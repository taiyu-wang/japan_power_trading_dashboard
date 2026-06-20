import pandas as pd
import src.news as news_module

from src.news import (
    _parse_dated_html_content,
    _parse_feed_content,
    filter_power_news,
    fetch_public_power_news_with_diagnostics,
    generation_outlook_pipeline_assessment,
    generation_outlook_pipeline_recommendations,
    japan_power_news_source_assessment,
    news_pipeline_recommendations,
    normalize_news_events,
    sample_power_news,
)


def test_news_source_assessment_has_public_and_paid_options():
    sources = japan_power_news_source_assessment()

    assert {"source", "coverage", "pipeline_fit", "access", "registration", "implementation_note", "url"}.issubset(sources.columns)
    assert sources["registration"].str.contains("Not required").any()
    assert sources["registration"].str.contains("Required").any()


def test_news_pipeline_recommendations_are_non_empty():
    recommendations = news_pipeline_recommendations()

    assert recommendations
    assert any("deduplication" in item for item in recommendations)


def test_generation_outlook_pipeline_covers_core_supply_lanes():
    lanes = generation_outlook_pipeline_assessment()

    assert {"outlook_lane", "primary_sources", "market_use", "latency", "data_shape", "registration", "priority", "url"}.issubset(lanes.columns)
    joined = " ".join(lanes["outlook_lane"])
    assert "Nuclear" in joined
    assert "Solar" in joined
    assert "OCCTO" in joined
    assert lanes["registration"].str.contains("Required").any()


def test_generation_outlook_recommendations_are_non_empty():
    recommendations = generation_outlook_pipeline_recommendations()

    assert recommendations
    assert any("Tokyo/Kansai" in item for item in recommendations)


def test_sample_power_news_has_dashboard_columns():
    news = sample_power_news()

    assert {"published_at", "source", "category", "title", "summary", "url", "market_tag", "impact_hint"}.issubset(news.columns)
    assert not news.empty


def test_filter_power_news_keeps_generation_outlook_items():
    raw = normalize_news_events(
        sample_power_news().assign(title=["Nuclear reactor restart watch", "Solar FIT pipeline update", "Unrelated macro note"])
    )

    filtered = filter_power_news(raw)

    assert filtered["title"].str.contains("Nuclear|Solar").any()


def test_feed_parser_supports_rss_and_atom():
    rss = b"""<rss><channel><item><title>Japan power market update</title><link>https://example.com/rss</link>
    <description>JEPX electricity notice</description><pubDate>Thu, 04 Jun 2026 00:00:00 GMT</pubDate></item></channel></rss>"""
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Japan LNG supply update</title>
    <link href="https://example.com/atom"/><summary>Power fuel outlook</summary><updated>2026-06-04T00:00:00Z</updated></entry></feed>"""

    rss_rows = _parse_feed_content(rss, "RSS source")
    atom_rows = _parse_feed_content(atom, "Atom source")

    assert rss_rows[0]["url"] == "https://example.com/rss"
    assert atom_rows[0]["url"] == "https://example.com/atom"
    assert atom_rows[0]["published_at"] == "2026-06-04T00:00:00Z"


def test_dated_html_parser_extracts_jepx_style_notice():
    content = b"""<html><body><a href="/electricpower/news/test.pdf">2026.06.04 JEPX market notice</a></body></html>"""

    rows = _parse_dated_html_content(content, "https://www.jepx.jp/electricpower/news/", "JEPX notices")

    assert rows[0]["published_at"] == "2026-06-04"
    assert rows[0]["title"] == "JEPX market notice"
    assert rows[0]["url"] == "https://www.jepx.jp/electricpower/news/test.pdf"


def test_strict_power_news_filter_does_not_return_unrelated_feed_items():
    raw = pd.DataFrame(
        {
            "published_at": ["2026-06-04"],
            "source": ["Generic feed"],
            "title": ["Equities market close"],
            "summary": ["Stocks ended higher."],
        }
    )

    assert filter_power_news(raw, fallback_to_latest=False).empty


def test_normalize_news_events_handles_mixed_timestamp_formats():
    raw = pd.DataFrame(
        {
            "published_at": ["Thu, 04 Jun 2026 00:00:00 GMT", "2026-05-28"],
            "source": ["Feed", "Official notice"],
            "title": ["Japan power update", "JEPX market notice"],
        }
    )

    normalized = normalize_news_events(raw)

    assert set(normalized["published_at"].dt.strftime("%Y-%m-%d")) == {"2026-06-04", "2026-05-28"}


def test_public_refresh_keeps_partial_success_and_reports_failed_source(monkeypatch):
    def good_source(url, source, timeout):
        return [
            {
                "published_at": "2026-06-04",
                "source": source,
                "title": "JEPX electricity market notice",
                "summary": "",
                "url": url,
            }
        ]

    def failed_source(url, source, timeout):
        raise TimeoutError("source timed out")

    monkeypatch.setattr(
        news_module,
        "_public_news_sources",
        lambda: [
            {"source": "Working source", "fetch": good_source, "url": "https://example.com/good"},
            {"source": "Slow source", "fetch": failed_source, "url": "https://example.com/slow"},
        ],
    )

    news, warnings, sources = fetch_public_power_news_with_diagnostics()

    assert not news.empty
    assert sources == ["Working source"]
    assert warnings == ["Slow source unavailable: TimeoutError."]
