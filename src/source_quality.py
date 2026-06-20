from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SourceStatus:
    source_label: str
    category: str
    confidence: str
    desk_use: str
    caveat: str


def classify_source_label(source_label: str | None) -> SourceStatus:
    """Classify a dashboard source label into trader-facing quality language."""
    label = (source_label or "").strip()
    lower = label.lower()

    if not label or "no local" in lower:
        return SourceStatus(
            source_label=label or "Unspecified",
            category="Unavailable",
            confidence="n/a",
            desk_use="No active dataset",
            caveat="Refresh, upload, or rebuild the processed dataset before relying on this screen.",
        )

    if "uploaded" in lower or "manual" in lower:
        return SourceStatus(
            source_label=label,
            category="Uploaded / analyst supplied",
            confidence="User dependent",
            desk_use="Potentially production-grade",
            caveat="Reliability depends on the provider, timestamp, unit, and settlement basis supplied by the desk.",
        )

    if "jepx public" in lower or "public bidding" in lower:
        return SourceStatus(
            source_label=label,
            category="Public exchange data",
            confidence="High for public aggregate",
            desk_use="Good for ex-post market-structure analysis",
            caveat="Not participant-level, not plant-level, and not a live order book.",
        )

    if "open-meteo" in lower:
        return SourceStatus(
            source_label=label,
            category="Public weather API",
            confidence="Medium",
            desk_use="Good for screening weather-price sensitivity",
            caveat="Grid/station basis should be reconciled against JMA or vendor weather for trading operations.",
        )

    if "live public" in lower:
        return SourceStatus(
            source_label=label,
            category="Public / derived live feed",
            confidence="Medium",
            desk_use="Good for market screening",
            caveat="Derived or delayed marks are not settlement-quality; replace key curves with exchange/vendor data.",
        )

    if "derived" in lower:
        return SourceStatus(
            source_label=label,
            category="Derived analytics",
            confidence="Input dependent",
            desk_use="Good for interpretation once inputs are validated",
            caveat="Check assumptions and upstream source quality before using the derived metric for trading decisions.",
        )

    if "processed japanesepower" in lower:
        return SourceStatus(
            source_label=label,
            category="Processed public aggregate",
            confidence="Medium",
            desk_use="Useful for supply-mix and residual thermal reads",
            caveat="Processed aggregates should be reconciled against official TSO, OCCTO, METI, or vendor data.",
        )

    if "processed public" in lower or "compact processed" in lower:
        return SourceStatus(
            source_label=label,
            category="Processed public dataset",
            confidence="Medium",
            desk_use="Useful for deployed analytics and market monitoring",
            caveat="Review processing date, source lineage, and aggregation logic before production use.",
        )

    if "processed compact jepx" in lower or "local jepx" in lower:
        return SourceStatus(
            source_label=label,
            category="Processed public cache",
            confidence="Medium-high",
            desk_use="Good for fast deployed stack diagnostics",
            caveat="Cache freshness depends on the local refresh process; raw exchange files are not loaded in deployed mode.",
        )

    if "bundled synthetic" in lower or "synthetic" in lower:
        return SourceStatus(
            source_label=label,
            category="Synthetic sample",
            confidence="Low",
            desk_use="Workflow demonstration only",
            caveat="Do not use synthetic sample values for trading decisions.",
        )

    if "bundled sample" in lower or "sample" in lower or "bundled fallback" in lower:
        return SourceStatus(
            source_label=label,
            category="Bundled sample / fallback",
            confidence="Low-screening",
            desk_use="Dashboard continuity and smoke testing",
            caveat="Replace with uploaded, public, or vendor data before production desk use.",
        )

    return SourceStatus(
        source_label=label,
        category="Unclassified",
        confidence="Review required",
        desk_use="Use with caution",
        caveat="Add an explicit source note if this dataset becomes part of the production workflow.",
    )


def source_status_table(sources: dict[str, str]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for dataset, source_label in sources.items():
        status = classify_source_label(source_label)
        rows.append(
            {
                "dataset": dataset,
                "source": status.source_label,
                "category": status.category,
                "confidence": status.confidence,
                "desk_use": status.desk_use,
                "caveat": status.caveat,
            }
        )
    return pd.DataFrame(rows)
