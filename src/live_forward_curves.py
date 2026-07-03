from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
from lxml import html

from .http_client import get_session


OILPRICE_BRENT_URL = "https://oilprice.com/futures/brent"
JPX_ELECTRICITY_REFERENCE_URL = "https://www.jpx.co.jp/english/markets/derivatives/reference/electricity/"
CURVE_END_DATE = pd.Timestamp("2027-12-31")
QUARTERLY_FROM = pd.Timestamp("2027-01-01")
LIVE_CURVE_COLUMNS = [
    "curve_date",
    "contract_month",
    "market",
    "region",
    "price",
    "currency",
    "unit",
    "contract_type",
    "source_note",
    "source_url",
    "tenor_label",
]


@dataclass(frozen=True)
class LiveCurveResult:
    data: pd.DataFrame
    warnings: list[str]


def _parse_contract_month(label: str) -> pd.Timestamp | None:
    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
        str(label),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return pd.Timestamp(f"{match.group(1).title()} 1 {match.group(2)}")


def _clean_number(value) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def fetch_brent_curve_oilprice() -> pd.DataFrame:
    response = get_session().get(
        OILPRICE_BRENT_URL,
        headers={"User-Agent": "Mozilla/5.0 market-dashboard"},
        timeout=8,
    )
    response.raise_for_status()
    doc = html.fromstring(response.text)
    contract_rows = doc.xpath("//div[contains(@class, 'info_table_row') and @data-symbol]")
    if not contract_rows:
        raise ValueError("Could not find Brent futures contract rows on Oilprice.com.")
    rows = []
    curve_date = pd.Timestamp.utcnow().normalize().tz_localize(None)
    for row in contract_rows:
        label = " ".join(row.xpath(".//a[contains(@class, 'contract-link')][1]//text()"))
        price_text = " ".join(row.xpath(".//div[contains(@class, 'last_price')]//text()"))
        contract_month = _parse_contract_month(label)
        price = _clean_number(price_text)
        if contract_month is None or price is None:
            continue
        rows.append(
            {
                "curve_date": curve_date,
                "contract_month": contract_month,
                "market": "BRENT",
                "region": "Global",
                "price": price,
                "currency": "USD",
                "unit": "bbl",
                "contract_type": "financial_futures",
                "source_note": f"Live/delayed Brent futures table scraped from Oilprice.com ({OILPRICE_BRENT_URL}); verify against ICE settlements for production use.",
            }
        )
    if not rows:
        raise ValueError("Brent futures table was found but no contract rows could be parsed.")
    return pd.DataFrame(rows).sort_values("contract_month").reset_index(drop=True)


def derive_jcc_from_brent(brent_curve: pd.DataFrame) -> pd.DataFrame:
    jcc = brent_curve.copy()
    jcc["market"] = "JCC"
    jcc["region"] = "Japan"
    jcc["price"] = (jcc["price"] * 0.92).round(4)
    jcc["contract_type"] = "monthly_customs_proxy_derived_from_live_brent"
    jcc["source_note"] = "Derived proxy from live Brent curve at 92% to approximate monthly Japan customs-cleared crude. Replace with official Japan customs statistics when available."
    return jcc


def derive_jcc_linked_lng_from_jcc(jcc_curve: pd.DataFrame, slope: float = 0.135, constant: float = 0.5) -> pd.DataFrame:
    lng = jcc_curve.copy()
    lng["market"] = "JCC_LINKED_LNG"
    lng["region"] = "Japan"
    lng["price"] = (lng["price"] * slope + constant).round(4)
    lng["unit"] = "MMBtu"
    lng["contract_type"] = "oil_linked_lng_proxy_derived_from_live_brent"
    lng["source_note"] = f"Derived from live Brent-based JCC proxy using slope {slope:.1%} plus {constant:.2f} USD/MMBtu constant. Replace with contract-specific formula."
    return lng


def apply_japan_forward_tenor_policy(curves: pd.DataFrame) -> pd.DataFrame:
    """Monthly through Dec-2026, then quarterly strips through end-2027."""
    if curves.empty:
        return curves
    out = curves[curves["contract_month"] <= CURVE_END_DATE].copy()
    monthly = out[out["contract_month"] < QUARTERLY_FROM].copy()
    quarterly_src = out[out["contract_month"] >= QUARTERLY_FROM].copy()
    if quarterly_src.empty:
        return monthly.sort_values(["market", "contract_month"]).reset_index(drop=True)

    quarterly_src["contract_quarter"] = quarterly_src["contract_month"].dt.to_period("Q")
    group_cols = ["curve_date", "market", "region", "currency", "unit", "contract_type", "source_note"]
    if "source_url" in quarterly_src.columns:
        group_cols.append("source_url")
    quarterly = quarterly_src.groupby(group_cols + ["contract_quarter"], as_index=False)["price"].mean()
    quarterly["contract_month"] = quarterly["contract_quarter"].dt.start_time
    quarterly["tenor_label"] = quarterly["contract_quarter"].astype(str)
    quarterly["price"] = quarterly["price"].round(4)
    quarterly = quarterly.drop(columns=["contract_quarter"])

    monthly["tenor_label"] = monthly["contract_month"].dt.strftime("%b-%y")
    return pd.concat([monthly, quarterly], ignore_index=True).sort_values(["market", "contract_month"]).reset_index(drop=True)


def required_vendor_curve_sources() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "JKM",
                "curve_required": "JKM LNG futures / Platts JKM derivatives",
                "status": "licensed_or_upload_required",
                "source_note": "JKM futures trade on ICE/CME/JPX and Platts publishes derivative assessments, but reliable settlement/forward prices require exchange/vendor access or user upload.",
            },
            {
                "market": "NEWCASTLE_COAL",
                "curve_required": "globalCOAL Newcastle coal futures",
                "status": "licensed_or_upload_required",
                "source_note": "ICE/globalCOAL Newcastle coal futures are Japan-relevant thermal coal references, but live settlement curves require ICE/vendor access or user upload.",
            },
            {
                "market": "CFR_JAPAN_COAL",
                "curve_required": "CFR Japan delivered coal / broker forward curve",
                "status": "licensed_or_upload_required",
                "source_note": "CFR Japan coal is typically assessed or brokered rather than available as a broad public free forward curve. Upload vendor/broker marks for live dashboarding.",
            },
        ]
    )


def fetch_live_forward_curves() -> LiveCurveResult:
    warnings = [
        "JPX states TOCOM electricity/LNG daily settlement CSV publication ended at end-March 2025; from April 2025 settlement history is available through paid JSCC service.",
        "JCC is not exchange-traded; live forward values are shown as Brent-derived proxy until official customs data or a licensed vendor feed is connected.",
    ]
    brent = fetch_brent_curve_oilprice()
    if brent.empty:
        warnings.append(
            "Brent fetch returned no contract rows; skipping derived JCC and JCC-linked LNG curves. Retry later or use the bundled fallback CSV."
        )
        return LiveCurveResult(pd.DataFrame(columns=LIVE_CURVE_COLUMNS), warnings)
    jcc = derive_jcc_from_brent(brent)
    jcc_linked = derive_jcc_linked_lng_from_jcc(jcc)
    curves = pd.concat([brent, jcc, jcc_linked], ignore_index=True)
    curves["source_url"] = OILPRICE_BRENT_URL
    curves = apply_japan_forward_tenor_policy(curves)
    return LiveCurveResult(curves, warnings)
