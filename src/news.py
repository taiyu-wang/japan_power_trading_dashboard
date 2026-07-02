from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlencode, urljoin

import pandas as pd
import requests
from lxml import html as lxml_html


NEWS_COLUMNS = ["published_at", "source", "category", "title", "summary", "url", "market_tag", "impact_hint"]
POWER_NEWS_KEYWORDS = [
    "electric",
    "power",
    "jepx",
    "occto",
    "nuclear",
    "reactor",
    "solar",
    "renewable",
    "lng",
    "coal",
    "grid",
    "supply",
    "demand",
    "capacity",
    "電力",
    "需給",
    "原子力",
    "太陽光",
    "再生可能",
    "火力",
    "取引",
    "市場",
    "時間前",
    "スポット",
    "先渡",
    "送電",
    "系統",
    "容量",
    "連系",
]
NEWS_NOISE_KEYWORDS = [
    "stock",
    "shares",
    "initial listing",
    "pro market",
    "nuclear fusion",
    "financial summary",
]
DATE_PATTERN = re.compile(
    r"(?P<year>20\d{2})\s*[./年 -]\s*(?P<month>\d{1,2})\s*[./月 -]\s*(?P<day>\d{1,2})日?"
)
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 japan-power-dashboard/1.0"}


def normalize_news_events(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    for col in NEWS_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["published_at"] = pd.to_datetime(out["published_at"], errors="coerce", utc=True, format="mixed").dt.tz_convert(None)
    if out["published_at"].isna().all():
        out["published_at"] = pd.Timestamp.today().normalize()
    out["published_at"] = out["published_at"].fillna(pd.Timestamp.today().normalize())
    for col in [c for c in NEWS_COLUMNS if c != "published_at"]:
        out[col] = out[col].fillna("").astype(str).str.strip()
    out = out[out["title"].ne("")]
    return out[NEWS_COLUMNS].drop_duplicates(["source", "title", "url"]).sort_values("published_at", ascending=False).reset_index(drop=True)


def classify_news_item(title: str, summary: str = "") -> tuple[str, str, str]:
    text = f"{title} {summary}".lower()
    if any(token in text for token in ["nuclear", "reactor", "原子力"]):
        return "Generation outlook", "Nuclear", "Baseload availability / regional supply watch"
    if any(token in text for token in ["solar", "renewable", "fit", "fip", "太陽光", "再生可能"]):
        return "Generation outlook", "Solar/Renewables", "Daytime supply growth / curtailment watch"
    if any(token in text for token in ["grid", "interconnection", "transmission", "occto", "capacity", "系統", "広域"]):
        return "System outlook", "Grid/Capacity", "Regional basis / adequacy watch"
    if any(token in text for token in ["lng", "coal", "thermal", "火力"]):
        return "Fuel stack", "Thermal/Fuel", "Thermal dispatch and SRMC watch"
    if any(token in text for token in ["jepx", "market", "trading"]):
        return "Market structure", "JEPX", "Market operation / liquidity watch"
    return "Market news", "Japan Power", "Monitor for desk relevance"


def filter_power_news(df: pd.DataFrame, fallback_to_latest: bool = True) -> pd.DataFrame:
    news = normalize_news_events(df)
    if news.empty:
        return news
    text = (news["title"] + " " + news["summary"]).str.lower()
    mask = text.apply(lambda value: any(keyword.lower() in value for keyword in POWER_NEWS_KEYWORDS))
    noise_mask = text.apply(lambda value: any(keyword in value for keyword in NEWS_NOISE_KEYWORDS))
    mask &= ~noise_mask
    filtered = news[mask].copy()
    if not filtered.empty or not fallback_to_latest:
        return filtered
    return news.head(20).copy()


def _element_name(element: ET.Element) -> str:
    return str(element.tag).rsplit("}", 1)[-1]


def _element_text(element: ET.Element, *names: str) -> str:
    for child in element.iter():
        if child is element or _element_name(child) not in names:
            continue
        return "".join(child.itertext()).strip()
    return ""


def _parse_feed_content(content: bytes, source: str, prefer_item_source: bool = False) -> list[dict[str, str]]:
    root = ET.fromstring(content)
    entries = [element for element in root.iter() if _element_name(element) in {"item", "entry"}]
    rows = []
    for item in entries[:40]:
        title = unescape(_element_text(item, "title")).strip()
        summary = re.sub(r"<[^>]+>", "", unescape(_element_text(item, "description", "summary", "content"))).strip()
        published = _element_text(item, "pubDate", "published", "updated", "date")
        link = _element_text(item, "link")
        if not link:
            link_element = next((child for child in item.iter() if _element_name(child) == "link"), None)
            link = link_element.attrib.get("href", "").strip() if link_element is not None else ""
        item_source = _element_text(item, "source")
        display_source = item_source if prefer_item_source and item_source else source
        category, market_tag, impact_hint = classify_news_item(title, summary)
        rows.append(
            {
                "published_at": published,
                "source": display_source,
                "category": category,
                "title": title,
                "summary": summary,
                "url": link,
                "market_tag": market_tag,
                "impact_hint": impact_hint,
            }
        )
    return rows


def _feed_items(url: str, source: str, timeout: int = 8, prefer_item_source: bool = False) -> list[dict[str, str]]:
    response = requests.get(url, timeout=(3.05, timeout), headers=HTTP_HEADERS)
    response.raise_for_status()
    return _parse_feed_content(response.content, source, prefer_item_source=prefer_item_source)


def _parse_dated_html_content(content: bytes, url: str, source: str) -> list[dict[str, str]]:
    document = lxml_html.fromstring(content)
    rows = []
    for anchor in document.xpath("//a[@href]"):
        anchor_text = " ".join(anchor.text_content().split())
        parent_text = " ".join(anchor.getparent().text_content().split()) if anchor.getparent() is not None else ""
        date_match = DATE_PATTERN.search(anchor_text) or DATE_PATTERN.search(parent_text)
        if not date_match:
            continue
        title = DATE_PATTERN.sub("", anchor_text, count=1).strip(" -|")
        if not title or title.lower() in {"view all", "more", "一覧へ"}:
            continue
        published = f"{date_match.group('year')}-{int(date_match.group('month')):02d}-{int(date_match.group('day')):02d}"
        category, market_tag, impact_hint = classify_news_item(title)
        rows.append(
            {
                "published_at": published,
                "source": source,
                "category": category,
                "title": title,
                "summary": "",
                "url": urljoin(url, anchor.attrib["href"]),
                "market_tag": market_tag,
                "impact_hint": impact_hint,
            }
        )
    return rows[:40]


def _dated_html_items(url: str, source: str, timeout: int = 8) -> list[dict[str, str]]:
    response = requests.get(url, timeout=(3.05, timeout), headers=HTTP_HEADERS)
    response.raise_for_status()
    return _parse_dated_html_content(response.content, url, source)


def _public_news_sources() -> list[dict[str, object]]:
    google_query = urlencode(
        {
            "q": '"Japan electricity" OR "Japan power market" OR JEPX OR "Japan nuclear plant" OR "Japan LNG power" -stock -shares -fusion when:30d',
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    return [
        {
            "source": "JEPX notices",
            "fetch": _dated_html_items,
            "url": "https://www.jepx.jp/electricpower/news/",
        },
        {
            "source": "OCCTO releases",
            "fetch": _dated_html_items,
            "url": "https://www.occto.or.jp/en/",
        },
        {
            "source": "Google News RSS",
            "fetch": _feed_items,
            "url": f"https://news.google.com/rss/search?{google_query}",
            "prefer_item_source": True,
        },
    ]


def _fetch_public_source(spec: dict[str, object], timeout: int) -> list[dict[str, str]]:
    fetch = spec["fetch"]
    kwargs = {"prefer_item_source": True} if spec.get("prefer_item_source") else {}
    return fetch(spec["url"], spec["source"], timeout=timeout, **kwargs)


def fetch_public_power_news_with_diagnostics(timeout: int = 8) -> tuple[pd.DataFrame, list[str], list[str]]:
    rows: list[dict[str, str]] = []
    warnings: list[str] = []
    successful_sources: list[str] = []
    sources = _public_news_sources()
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {executor.submit(_fetch_public_source, spec, timeout): str(spec["source"]) for spec in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                source_rows = future.result()
                successful_sources.append(source)
                rows.extend(source_rows)
            except Exception as exc:
                warnings.append(f"{source} unavailable: {type(exc).__name__}.")
    if not rows:
        return pd.DataFrame(columns=NEWS_COLUMNS), sorted(warnings), sorted(successful_sources)
    news = filter_power_news(pd.DataFrame(rows), fallback_to_latest=False)
    source_priority = {"JEPX notices": 0, "OCCTO releases": 1, "METI releases": 2}
    news["_source_priority"] = news["source"].map(source_priority).fillna(3)
    news = news.sort_values(["published_at", "_source_priority"], ascending=[False, True]).drop(columns="_source_priority")
    return news.head(60).reset_index(drop=True), sorted(warnings), sorted(successful_sources)


def fetch_public_power_news(timeout: int = 10) -> pd.DataFrame:
    news, _, _ = fetch_public_power_news_with_diagnostics(timeout=timeout)
    return news


def sample_power_news() -> pd.DataFrame:
    today = pd.Timestamp.today().normalize()
    rows = [
        {
            "published_at": today,
            "source": "Sample pipeline",
            "category": "Generation outlook",
            "title": "Kansai nuclear availability remains key baseload swing factor for summer",
            "summary": "Sample desk headline showing how reactor status would be tagged for regional supply monitoring.",
            "url": "https://www.nra.go.jp/english/e_nra/plants_Info.html",
            "market_tag": "Nuclear",
            "impact_hint": "Baseload availability / regional supply watch",
        },
        {
            "published_at": today - pd.Timedelta(days=1),
            "source": "Sample pipeline",
            "category": "Generation outlook",
            "title": "METI FIT/FIP solar disclosure points to continued daytime supply growth",
            "summary": "Sample desk headline for solar project pipeline and daytime price-shape monitoring.",
            "url": "https://www.fit-portal.go.jp/PublicInfoSummary",
            "market_tag": "Solar/Renewables",
            "impact_hint": "Daytime supply growth / curtailment watch",
        },
        {
            "published_at": today - pd.Timedelta(days=2),
            "source": "Sample pipeline",
            "category": "System outlook",
            "title": "OCCTO supply plan update remains central for reserve margin and grid adequacy tracking",
            "summary": "Sample desk headline for supply plan, reserve margin, and regional adequacy monitoring.",
            "url": "https://www.occto.or.jp/en/works/no10.html",
            "market_tag": "Grid/Capacity",
            "impact_hint": "Regional basis / adequacy watch",
        },
    ]
    return normalize_news_events(pd.DataFrame(rows))


def japan_power_news_source_assessment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "JEPX electricity trading notices",
                "coverage": "Exchange rule changes, intraday/spot/forward notices, market-operation updates",
                "pipeline_fit": "High",
                "access": "Public HTML scrape; no API found",
                "registration": "Not required",
                "implementation_note": "Poll daily, parse title/date/url, classify as market operation, rule change, outage/system, or auction notice.",
                "url": "https://www.jepx.jp/electricpower/news/",
            },
            {
                "source": "JEPX market monitoring reports",
                "coverage": "Seasonal market monitoring reports and oversight material",
                "pipeline_fit": "Medium",
                "access": "Public HTML/PDF scrape",
                "registration": "Not required",
                "implementation_note": "Best used as slower-moving context; extract report date, season, and affected market themes.",
                "url": "https://www.jepx.jp/electricpower/reports/",
            },
            {
                "source": "OCCTO news and disclosures",
                "coverage": "Supply-demand outlooks, supply plans, capacity market, grid/interconnection disclosures",
                "pipeline_fit": "High",
                "access": "Public HTML/PDF scrape",
                "registration": "Not required",
                "implementation_note": "Poll disclosure pages and tag items for supply-demand, capacity, grid, balancing, or regional risk.",
                "url": "https://www.occto.or.jp/en/",
            },
            {
                "source": "METI RSS",
                "coverage": "Policy releases, statistics updates, energy/electricity ministry announcements",
                "pipeline_fit": "Medium",
                "access": "RSS feed",
                "registration": "Not required",
                "implementation_note": "Use RSS for ingestion, then keyword-filter for electricity, power supply, fuel, subsidy, nuclear, LNG, coal, renewable.",
                "url": "https://www.meti.go.jp/rss/",
            },
            {
                "source": "JPX RSS",
                "coverage": "JPX group news, market news, derivatives and TOCOM-related announcements",
                "pipeline_fit": "Medium",
                "access": "RSS feed",
                "registration": "Not required",
                "implementation_note": "Useful for exchange/futures context; filter for electricity, TOCOM, JEPX, JSCC, power futures.",
                "url": "https://www.jpx.co.jp/english/rss/",
            },
            {
                "source": "Google News RSS",
                "coverage": "Broader public-media headlines on Japan power, JEPX, nuclear, LNG, and electricity",
                "pipeline_fit": "Medium as enrichment",
                "access": "Public RSS search; not a guaranteed API",
                "registration": "Not required",
                "implementation_note": "Use only as secondary enrichment behind official notices; keyword-filter and exclude equity-market noise.",
                "url": "https://news.google.com/rss",
            },
            {
                "source": "Commercial energy news",
                "coverage": "Near-real-time Japan power, LNG, coal, policy, outages, and utility desk news",
                "pipeline_fit": "High for trading desk, paid",
                "access": "Licensed API/feed",
                "registration": "Required",
                "implementation_note": "Use if available for production signals; preferred for low-latency desk commentary and event tagging.",
                "url": "Vendor dependent",
            },
        ]
    )


def news_pipeline_recommendations() -> list[str]:
    return [
        "Use JEPX and OCCTO notices as the authoritative public-news layer; use Google News RSS only as secondary enrichment.",
        "Do not place the slow METI feed on the interactive refresh path; ingest it in a scheduled background job if policy coverage is needed.",
        "Store raw headlines, published timestamp, source, URL, language, extracted keywords, and a market-impact tag.",
        "Do not merge raw news directly into trading signals until deduplication and source-priority scoring are in place.",
        "Use paid/vendor news only if you need low-latency outage, fuel procurement, utility, and policy headlines.",
    ]


def generation_outlook_pipeline_assessment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "outlook_lane": "Nuclear restart / outage pipeline",
                "primary_sources": "NRA plant information; METI/ANRE nuclear restart updates; utility press releases",
                "market_use": "Track reactor restart probability, inspection status, local approval risk, and expected baseload supply additions.",
                "latency": "Weekly to event-driven",
                "data_shape": "plant, unit, operator, region, status, capacity_mw, milestone_date, source_url",
                "registration": "Not required for public pages",
                "priority": "High",
                "url": "https://www.nra.go.jp/english/e_nra/plants_Info.html",
            },
            {
                "outlook_lane": "Solar / renewable project pipeline",
                "primary_sources": "METI FIT/FIP PublicInfo; ANRE renewable pages; local utility interconnection status pages",
                "market_use": "Monitor approved versus commissioned solar capacity, delayed projects, curtailment exposure, and daytime price cannibalization risk.",
                "latency": "Monthly / publication-driven",
                "data_shape": "project or aggregate, prefecture, technology, certified_kw, commissioned_kw, FIT/FIP status, disclosure_date",
                "registration": "Not required for public FIT/FIP disclosure; scraping/parser needed",
                "priority": "High",
                "url": "https://www.fit-portal.go.jp/PublicInfoSummary",
            },
            {
                "outlook_lane": "OCCTO supply plan and reserve outlook",
                "primary_sources": "OCCTO supply plan aggregation; OCCTO supply-demand outlook; demand forecast by supply area",
                "market_use": "Track reserve margin, planned generation capacity, retirements, new builds, demand assumptions, and regional supply adequacy.",
                "latency": "Annual / seasonal updates",
                "data_shape": "fiscal_year, area, fuel_type, capacity_mw, supply_capacity_mw, reserve_margin, source_document",
                "registration": "Not required; PDF/Excel extraction likely",
                "priority": "High",
                "url": "https://www.occto.or.jp/en/works/no10.html",
            },
            {
                "outlook_lane": "Grid / interconnection / curtailment constraint pipeline",
                "primary_sources": "OCCTO grid master plan; TSO renewable connection status pages; supply-area curtailment notices",
                "market_use": "Assess whether new solar/wind capacity is deliverable, constrained, or exposed to curtailment; useful for regional basis and midday shape.",
                "latency": "Monthly to committee/publication-driven",
                "data_shape": "area, node_or_prefecture, technology, connection_status, curtailment_rule, capacity_kw, publication_date",
                "registration": "Not required for public pages; fragmented by utility",
                "priority": "Medium",
                "url": "https://www.occto.or.jp/en/",
            },
            {
                "outlook_lane": "Thermal build / retirement / maintenance pipeline",
                "primary_sources": "OCCTO supply plans; utility integrated reports; utility press releases; METI committee materials",
                "market_use": "Track coal/LNG/oil capacity additions, retirements, mothballs, outages, and major maintenance affecting marginal fuel burn.",
                "latency": "Event-driven / annual plan refresh",
                "data_shape": "plant, unit, operator, area, fuel, capacity_mw, event_type, start_date, end_date, confidence",
                "registration": "Public sources available, but vendor plant-outage feeds are better for trading latency",
                "priority": "High with vendor, Medium public-only",
                "url": "https://www.occto.or.jp/en/information_disclosure/supply_plan/",
            },
            {
                "outlook_lane": "Offshore wind / auction pipeline",
                "primary_sources": "METI/MLIT offshore wind auction announcements; ANRE renewable policy pages; developer press releases",
                "market_use": "Longer-term supply mix and regional basis context; limited short-term trading impact until construction and grid milestones firm.",
                "latency": "Tender / project milestone driven",
                "data_shape": "auction_round, sea_area, developer, capacity_mw, award_date, expected_cod, grid_area",
                "registration": "Not required",
                "priority": "Medium",
                "url": "https://www.meti.go.jp/english/policy/energy_environment/renewable/index.html",
            },
            {
                "outlook_lane": "Commercial generation/outage news",
                "primary_sources": "Paid energy news, plant outage vendors, broker notes, utility intelligence",
                "market_use": "Low-latency confirmation of nuclear, thermal, renewable, fuel procurement, and grid events for signal scoring.",
                "latency": "Intraday to daily",
                "data_shape": "headline, timestamp, source, asset, area, fuel, event_type, expected_market_impact, confidence",
                "registration": "Required",
                "priority": "High for production trading desk",
                "url": "Vendor dependent",
            },
        ]
    )


def generation_outlook_pipeline_recommendations() -> list[str]:
    return [
        "Start with nuclear restart/outage status, FIT/FIP solar pipeline, and OCCTO supply-plan extraction because these most directly change expected supply stack.",
        "Use public pages for strategic outlook and add paid/vendor feeds only if intraday outage latency becomes important.",
        "Standardize every record into area, asset/fuel, capacity MW, milestone date, event type, source URL, and confidence before linking it to trading signals.",
        "For Tokyo/Kansai trading views, map national/prefecture records into East/West/JEPX area exposure; do not assume national additions affect both regions equally.",
    ]
