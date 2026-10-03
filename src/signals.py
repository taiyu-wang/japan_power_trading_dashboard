import numpy as np
import pandas as pd

from .indicators import calculate_srmc_comparison, spread_suite
from .transformations import calculate_curve_steepness, pivot_prices
from .market_context import VERIFIED_SOURCES, aligned_changes, eligible_history, japan_today


SIGNAL_COLUMNS = [
    "signal_time_sgt",
    "market_data_as_of",
    "signal_name",
    "direction",
    "confidence_score",
    "rationale",
    "trader_interpretation",
    "possible_market_implication",
    "invalidation",
    "supporting_metrics",
    "explanation",
    "evidence_strength",
]

SIGNAL_METHODOLOGY = [
    {
        "signal_name": "Gas SRMC premium widening",
        "trigger": "JKM gas SRMC 30d % change minus coal SRMC 30d % change > 5 pts, and latest gas SRMC is above coal SRMC.",
        "inputs": "JKM, selected coal reference, USDJPY, JEPX system; SRMC uses gas efficiency 55%, coal efficiency 40%, coal heat content 6,000 kcal/kg, VOM assumptions.",
        "confidence": "58 + 1.4 x absolute relative SRMC performance gap, capped at 95.",
        "read": "Coal is advantaged in the dispatch stack when gas SRMC is widening versus coal.",
    },
    {
        "signal_name": "Spark spread compression",
        "trigger": "JKM gas SRMC 30d % change minus JEPX system 30d % change > 6 pts, and latest JEPX is below JKM gas SRMC.",
        "inputs": "JKM gas SRMC and JEPX system price.",
        "confidence": "58 + 1.2 x absolute SRMC-versus-power performance gap, capped at 94.",
        "read": "Gas-fired economics are compressed unless power reprices or LNG weakens.",
    },
    {
        "signal_name": "LNG premium widening",
        "trigger": "JKM 30d % change minus Newcastle coal 30d % change > 8 pts.",
        "inputs": "JKM and Newcastle coal outright prices.",
        "confidence": "55 + 1.0 x absolute relative performance gap, capped at 95.",
        "read": "Relative benchmark performance is diverging; dispatch competitiveness requires same-unit SRMC confirmation.",
    },
    {
        "signal_name": "Coal competitiveness shift",
        "trigger": "JKM 30d % change minus Newcastle coal 30d % change < -6 pts.",
        "inputs": "JKM and Newcastle coal outright prices.",
        "confidence": "55 + 1.0 x absolute relative performance gap, capped at 90.",
        "read": "Coal has outperformed LNG; verify FX, delivered cost and efficiency before inferring a dispatch change.",
    },
    {
        "signal_name": "JKM vs oil-linked dislocation",
        "trigger": "Absolute gap between JKM 30d % change and JCC-linked LNG proxy 30d % change > 7 pts.",
        "inputs": "JKM and JCC-linked LNG proxy.",
        "confidence": "54 + 1.1 x absolute spot-versus-oil-linked performance gap, capped at 94.",
        "read": "Spot LNG and oil-linked procurement economics are diverging.",
    },
    {
        "signal_name": "Power underreaction to fuel rally",
        "trigger": "JKM 30d % change is positive and exceeds JEPX system 30d % change by > 8 pts on matched dates.",
        "inputs": "JKM and JEPX system price.",
        "confidence": "55 + 1.0 x absolute fuel-versus-power lag, capped at 92.",
        "read": "Power may be lagging fuel input costs.",
    },
    {
        "signal_name": "Tokyo-Kansai divergence",
        "trigger": "Absolute z-score of Tokyo minus Kansai across the last 90 common daily observations > 1.5.",
        "inputs": "JEPX Tokyo and JEPX Kansai prices.",
        "confidence": "50 + 18 x absolute spread z-score, capped at 95.",
        "read": "Regional basis is stretched versus recent history.",
    },
    {
        "signal_name": "Spot-intraday divergence",
        "trigger": "Absolute z-score of system minus intraday across the last 60 common daily observations > 1.4.",
        "inputs": "JEPX system and JEPX intraday prices.",
        "confidence": "50 + 16 x absolute spread z-score, capped at 90.",
        "read": "Intraday pricing is not confirming day-ahead levels.",
    },
    {
        "signal_name": "Volatility breakout regime",
        "trigger": "JEPX system 30d annualized realized volatility > 1.25 x 90d annualized realized volatility.",
        "inputs": "JEPX system daily returns.",
        "confidence": "55 + 70 x volatility ratio excess over 1.0, capped at 96.",
        "read": "Short-dated optionality and risk limits deserve more attention.",
    },
    {
        "signal_name": "Cooling degree stress breakout",
        "trigger": "Tokyo plus Kansai cooling degree days are > 1.5z versus the 60d range and latest stress is positive.",
        "inputs": "Dated non-sample Tokyo/Kansai degree days, with both regions observed on each day.",
        "confidence": "55 + 14 x degree-day z-score, capped at 90.",
        "read": "Weather-sensitive load risk is elevated.",
    },
    {
        "signal_name": "Heating degree stress breakout",
        "trigger": "Tokyo plus Kansai heating degree days are > 1.5z versus the 60d range and latest stress is positive.",
        "inputs": "Dated non-sample Tokyo/Kansai degree days, with both regions observed on each day.",
        "confidence": "55 + 14 x degree-day z-score, capped at 90.",
        "read": "Winter weather-sensitive demand risk is elevated.",
    },
    {
        "signal_name": "Curve contango",
        "trigger": "At least 12 unexpired quoted tenors; 12th exceeds first by > 5%, on a curve no older than four days.",
        "inputs": "Forward curve by market, curve date, and contract month.",
        "confidence": "55 + absolute back/front premium in percent, capped at 88.",
        "read": "Deferred premium is priced into the curve; check roll and carry.",
    },
    {
        "signal_name": "Curve backwardation",
        "trigger": "At least 12 unexpired quoted tenors; 12th is > 5% below first, on a curve no older than four days.",
        "inputs": "Forward curve by market, curve date, and contract month.",
        "confidence": "55 + absolute back/front premium in percent, capped at 88.",
        "read": "Nearby premium is priced; separate seasonal shape from actual roll exposure.",
    },
]


def signal_methodology() -> pd.DataFrame:
    out = pd.DataFrame(SIGNAL_METHODOLOGY)
    out["confidence"] = "Heuristic evidence strength, not a forecast probability. " + out["confidence"]
    return out


def _pct_change(prices: pd.DataFrame, market: str, days: int = 30) -> float:
    changes, _ = aligned_changes(prices, [market], days)
    return changes.get(market, np.nan)


def _zscore(series: pd.Series, window: int) -> float:
    tail = series.dropna().tail(window)
    if len(tail) < max(20, window // 3) or tail.std() == 0:
        return np.nan
    return float((tail.iloc[-1] - tail.mean()) / tail.std())


def _confidence(base: float, driver: float, scale: float = 1.0, cap: float = 96) -> float:
    if pd.isna(driver):
        return base
    return min(cap, base + abs(driver) * scale)


def generate_market_commentary(df: pd.DataFrame) -> list[str]:
    df = eligible_history(df)
    if df.empty:
        return ["Current commentary is unavailable: refresh dated public or desk-supplied observations."]
    prices = pivot_prices(df)
    comments = []
    changes, _ = aligned_changes(prices, ["JKM", "JEPX_SYSTEM"])
    jkm, power = changes.get("JKM", np.nan), changes.get("JEPX_SYSTEM", np.nan)
    fuel_changes, _ = aligned_changes(prices, ["JKM", "NEWCASTLE_COAL"])
    coal = fuel_changes.get("NEWCASTLE_COAL", np.nan)
    matched_jkm = fuel_changes.get("JKM", np.nan)
    tokyo_vol_now = prices.get("JEPX_TOKYO", pd.Series(dtype=float)).pct_change().rolling(30).std().iloc[-1] if "JEPX_TOKYO" in prices else np.nan
    tokyo_vol_prev = prices.get("JEPX_TOKYO", pd.Series(dtype=float)).pct_change().rolling(30).std().iloc[-60] if "JEPX_TOKYO" in prices and len(prices) > 60 else np.nan
    if pd.notna(jkm) and pd.notna(power):
        verb = "rallied" if jkm > 0 else "weakened"
        lag = "leaving fuel-cost catch-up risk" if power < jkm - 5 else "with JEPX broadly tracking fuel beta"
        comments.append(f"JKM {verb} {abs(jkm):.1f}% m/m; JEPX system {power:.1f}% {lag}.")
    if pd.notna(coal) and pd.notna(matched_jkm):
        rel = "underperformed LNG" if coal < matched_jkm else "outperformed LNG"
        comments.append(f"Newcastle coal {rel} over the matched 30-day window; compare converted fuel costs before inferring a dispatch advantage.")
    if pd.notna(tokyo_vol_now) and pd.notna(tokyo_vol_prev):
        direction = "increased" if tokyo_vol_now > tokyo_vol_prev * 1.2 else "remained contained"
        comments.append(f"Tokyo realized volatility {direction} versus the prior 30d regime.")
    return comments or ["Insufficient lookback for a clean desk read; widen the window or add market history."]


def generate_trading_signals(df: pd.DataFrame, curves: pd.DataFrame, weather: pd.DataFrame | None = None, *, as_of=None, srmc_settings: dict | None = None) -> pd.DataFrame:
    cutoff = pd.Timestamp(as_of).normalize() if as_of is not None else japan_today()
    df = eligible_history(df, cutoff)
    prices = pivot_prices(df)
    spreads = spread_suite(df)
    rows = []
    signal_time_sgt = pd.Timestamp.now(tz="Asia/Singapore").strftime("%Y-%m-%d %H:%M:%S SGT")

    def add(
        name: str,
        direction: str,
        confidence: float,
        rationale: str,
        trader_interpretation: str,
        possible_market_implication: str,
        invalidation: str,
        metric: str,
        evidence_date=None,
    ) -> None:
        inputs = {
            "Gas SRMC premium widening": ["JKM", "JCC", "USDJPY", "JEPX_SYSTEM"],
            "Spark spread compression": ["JKM", "JCC", "USDJPY", "JEPX_SYSTEM"],
            "LNG premium widening": ["JKM", "NEWCASTLE_COAL"],
            "Coal competitiveness shift": ["JKM", "NEWCASTLE_COAL"],
            "JKM vs oil-linked dislocation": ["JKM", "JCC_LINKED_LNG"],
            "Power underreaction to fuel rally": ["JKM", "JEPX_SYSTEM"],
            "Tokyo-Kansai divergence": ["JEPX_TOKYO", "JEPX_KANSAI"],
            "Spot-intraday divergence": ["JEPX_SYSTEM", "JEPX_INTRADAY"],
        }.get(name, ["JEPX_SYSTEM"])
        if evidence_date is None:
            _, evidence_date = aligned_changes(prices, inputs)
        if evidence_date is None:
            return
        max_age = 7 if "degree stress" in name else 4
        if pd.Timestamp(evidence_date) < cutoff - pd.Timedelta(days=max_age):
            return
        rows.append(
            {
                "signal_time_sgt": signal_time_sgt,
                "market_data_as_of": pd.Timestamp(evidence_date).strftime("%Y-%m-%d"),
                "signal_name": name,
                "direction": direction,
                "confidence_score": round(float(confidence), 0),
                "rationale": rationale,
                "trader_interpretation": trader_interpretation,
                "possible_market_implication": possible_market_implication,
                "invalidation": invalidation,
                "supporting_metrics": metric,
                "explanation": rationale,
                "evidence_strength": "Strong" if confidence >= 80 else "Moderate" if confidence >= 65 else "Limited",
            }
        )

    fuel_changes, _ = aligned_changes(prices, ["JKM", "NEWCASTLE_COAL"])
    jkm_30 = fuel_changes.get("JKM", np.nan)
    coal_30 = fuel_changes.get("NEWCASTLE_COAL", np.nan)
    power_30 = _pct_change(prices, "JEPX_SYSTEM")
    srmc = calculate_srmc_comparison(df, **(srmc_settings or {})).reset_index(drop=True)
    if not srmc.empty and len(srmc.dropna(subset=["coal_srmc", "jkm_gas_srmc", "jepx_system"])) > 35:
        srmc_idx = srmc.dropna(subset=["coal_srmc", "jkm_gas_srmc", "jepx_system"]).set_index("date")
        coal_srmc_30 = _pct_change(srmc_idx[["coal_srmc"]].rename(columns={"coal_srmc": "COAL_SRMC"}), "COAL_SRMC")
        jkm_srmc_30 = _pct_change(srmc_idx[["jkm_gas_srmc"]].rename(columns={"jkm_gas_srmc": "JKM_SRMC"}), "JKM_SRMC")
        power_srmc_30 = _pct_change(srmc_idx[["jepx_system"]].rename(columns={"jepx_system": "JEPX_SYSTEM"}), "JEPX_SYSTEM")
        latest_srmc = srmc.dropna(subset=["coal_srmc", "jkm_gas_srmc", "jepx_system"]).sort_values("date").iloc[-1]
        jkm_premium_to_coal = latest_srmc["jkm_gas_srmc"] - latest_srmc["coal_srmc"]
        power_margin_to_jkm = latest_srmc["jepx_system"] - latest_srmc["jkm_gas_srmc"]
        if pd.notna(jkm_srmc_30) and pd.notna(coal_srmc_30) and jkm_srmc_30 - coal_srmc_30 > 5 and jkm_premium_to_coal > 0:
            gap = jkm_srmc_30 - coal_srmc_30
            add(
                "Gas SRMC premium widening",
                "Coal advantaged in dispatch stack",
                _confidence(58, gap, 1.4, 95),
                f"JKM gas SRMC widened {gap:.1f} pts versus coal SRMC over 30d; latest gas premium is {jkm_premium_to_coal:.2f} JPY/kWh.",
                "Coal screens cheaper than spot LNG on dispatch economics, after FX and efficiency assumptions.",
                "Gas-to-power repricing risk rises if LNG remains marginal despite the coal advantage.",
                "Invalidated if coal SRMC rises above gas SRMC or JKM gas SRMC retraces.",
                f"JKM gas SRMC 30d: {jkm_srmc_30:.1f}%; coal SRMC 30d: {coal_srmc_30:.1f}%; gas premium: {jkm_premium_to_coal:.2f} JPY/kWh",
                evidence_date=latest_srmc["date"],
            )
        if pd.notna(jkm_srmc_30) and pd.notna(power_srmc_30) and jkm_srmc_30 - power_srmc_30 > 6 and power_margin_to_jkm < 0:
            gap = jkm_srmc_30 - power_srmc_30
            add(
                "Spark spread compression",
                "JEPX below JKM gas SRMC",
                _confidence(58, gap, 1.2, 94),
                f"JKM gas SRMC outpaced JEPX by {gap:.1f} pts over 30d; latest JEPX margin to JKM SRMC is {power_margin_to_jkm:.2f} JPY/kWh.",
                "Thermal economics screen compressed for gas-fired generation.",
                "Either JEPX reprices higher, gas weakens, or gas-fired dispatch remains out of merit.",
                "Invalidated if JEPX clears back above gas SRMC or LNG cost falls.",
                f"JEPX 30d: {power_srmc_30:.1f}%; JKM gas SRMC 30d: {jkm_srmc_30:.1f}%; margin: {power_margin_to_jkm:.2f} JPY/kWh",
                evidence_date=latest_srmc["date"],
            )

    if pd.notna(jkm_30) and pd.notna(coal_30):
        diff = jkm_30 - coal_30
        if diff > 8:
            add(
                "LNG premium widening",
                "LNG outperforming coal benchmarks",
                _confidence(55, diff, 1.0, 95),
                f"JKM outperformed Newcastle coal by {diff:.1f} pts over 30d.",
                "LNG benchmark performance is stronger. Confirm dispatch competitiveness using delivered costs, FX and heat rates.",
                "Japan power may need higher clearing prices if LNG sets marginal supply more often.",
                "Signal weakens if coal rallies, JKM retraces, or JEPX reprices sharply higher.",
                f"JKM 30d: {jkm_30:.1f}%; Newcastle 30d: {coal_30:.1f}%",
            )
        elif diff < -6:
            add(
                "Coal competitiveness shift",
                "Coal benchmark outperforming LNG",
                _confidence(55, diff, 1.0, 90),
                f"Newcastle coal outperformed JKM by {abs(diff):.1f} pts over 30d.",
                "Coal benchmark performance is stronger; compare delivered SRMC before inferring a loss of dispatch advantage.",
                "A narrowing delivered gas-coal cost gap could affect dispatch only where plant availability and operating constraints allow.",
                "Invalidated by renewed coal weakness or LNG strength reversing the relative move.",
                f"JKM minus coal 30d performance gap: {diff:.1f} pts",
            )

    oil_changes, _ = aligned_changes(prices, ["JKM", "JCC_LINKED_LNG"])
    jkm_30, jcc_30 = oil_changes.get("JKM", np.nan), oil_changes.get("JCC_LINKED_LNG", np.nan)
    if pd.notna(jkm_30) and pd.notna(jcc_30):
        oil_linked_gap = jkm_30 - jcc_30
        if abs(oil_linked_gap) > 7:
            add(
                "JKM vs oil-linked dislocation",
                "Watch spot LNG versus JCC-linked procurement",
                _confidence(54, oil_linked_gap, 1.1, 94),
                f"JKM moved {oil_linked_gap:.1f} pts versus the JCC-linked LNG proxy over 30d.",
                "Spot procurement and oil-linked contract economics are diverging.",
                "Portfolio optimization value rises when spot and contract slopes decouple.",
                "Signal fades if Brent/JCC-linked LNG catches up or JKM normalizes.",
                f"JKM 30d: {jkm_30:.1f}%; JCC-linked LNG 30d: {jcc_30:.1f}%",
            )

    power_changes, _ = aligned_changes(prices, ["JKM", "JEPX_SYSTEM"])
    jkm_30, power_30 = power_changes.get("JKM", np.nan), power_changes.get("JEPX_SYSTEM", np.nan)
    if pd.notna(jkm_30) and pd.notna(power_30) and jkm_30 > 0 and jkm_30 - power_30 > 8:
        gap = jkm_30 - power_30
        add(
            "Power underreaction to fuel rally",
            "Fuel rally not confirmed by power",
            _confidence(55, gap, 1.0, 92),
            f"JKM rallied {gap:.1f} pts more than JEPX system prices over 30d.",
            "Power is lagging the fuel input move; watch for delayed thermal repricing.",
            "Catch-up risk is skewed higher if demand or outages force marginal LNG burn.",
            "Invalidated if JEPX remains demand-led, LNG retraces, or coal caps marginal cost.",
            f"JKM 30d: {jkm_30:.1f}%; JEPX system 30d: {power_30:.1f}%",
        )

    tk = spreads[spreads["market"] == "Tokyo minus Kansai"].dropna()
    if len(tk) > 90:
        latest = tk["price"].iloc[-1]
        z = _zscore(tk["price"], 90)
        if abs(z) > 1.5:
            add(
                "Tokyo-Kansai divergence",
                "Tokyo premium elevated" if z > 0 else "Kansai premium elevated",
                _confidence(50, z, 18, 95),
                f"Tokyo-Kansai basis is {z:.1f} standard deviations from the last 90 common daily observations.",
                "Regional basis is stretched and may reflect load, transfer, or outage dislocation.",
                "Basis spread deserves priority monitoring over outright power beta.",
                "Invalidated by congestion normalization or regional demand/weather convergence.",
                f"Latest spread: {latest:.2f} JPY/kWh; 90-observation z-score: {z:.2f}",
            )

    si = spreads[spreads["market"] == "Spot minus intraday"].dropna()
    if len(si) > 60:
        latest = si["price"].iloc[-1]
        z = _zscore(si["price"], 60)
        if abs(z) > 1.4:
            add(
                "Spot-intraday divergence",
                "Monitor balancing tightness",
                _confidence(50, z, 16, 90),
                f"Spot-intraday spread is {z:.1f} standard deviations from the last 60 common daily observations.",
                "Intraday pricing is not confirming day-ahead levels cleanly.",
                "Balancing volatility or short-term physical tightness may be underpriced.",
                "Signal weakens if intraday converges back to day-ahead or liquidity is thin.",
                f"Latest spread: {latest:.2f} JPY/kWh; 60-observation z-score: {z:.2f}",
            )

    if "JEPX_SYSTEM" in prices:
        vol30 = prices["JEPX_SYSTEM"].pct_change().rolling(30).std().iloc[-1] * np.sqrt(252) * 100
        vol90 = prices["JEPX_SYSTEM"].pct_change().rolling(90).std().iloc[-1] * np.sqrt(252) * 100
        if pd.notna(vol30) and pd.notna(vol90) and vol30 > vol90 * 1.25:
            vol_ratio = vol30 / vol90
            add(
                "Volatility breakout regime",
                "Vol bid / wider optionality value",
                _confidence(55, vol_ratio - 1, 70, 96),
                f"JEPX 30d realized volatility is {vol_ratio:.2f}x the 90d regime.",
                "Short-dated optionality and risk limits matter more than flat-price level alone.",
                "Spread and structured exposure should be sized for wider intraday moves.",
                "Invalidated if realized volatility compresses back toward the 90d regime.",
                f"30d vol: {vol30:.1f}%; 90d vol: {vol90:.1f}%",
            )

    if weather is not None and not weather.empty and "source" in weather:
        weather = weather.copy()
        weather["date"] = pd.to_datetime(weather["date"], errors="coerce")
        weather = weather[weather["date"].le(cutoff) & ~weather["source"].str.contains("sample|synthetic", case=False, na=True)]
        if "region" not in weather:
            weather = weather.iloc[:0]
        else:
            weather = weather[weather["region"].isin(["Tokyo", "Kansai"])]
            weather = weather.drop_duplicates(["date", "region"])
            count = weather.groupby("date")["region"].transform("nunique")
            weather = weather[count.eq(2)]
        weather_latest = weather["date"].max()
        if pd.isna(weather_latest) or weather_latest < cutoff - pd.Timedelta(days=7):
            weather = weather.iloc[:0]
        for stress_col, signal_name, direction in [
            ("cooling_degree_day", "Cooling degree stress breakout", "Weather-led power upside risk"),
            ("heating_degree_day", "Heating degree stress breakout", "Winter demand confirmation watch"),
        ]:
            if stress_col not in weather:
                continue
            daily_stress = weather.groupby("date", as_index=False)[stress_col].sum(min_count=2).dropna().sort_values("date")
            if len(daily_stress) > 60:
                stress_z = _zscore(daily_stress[stress_col], 60)
                latest_stress = daily_stress[stress_col].iloc[-1]
                if pd.notna(stress_z) and stress_z > 1.5 and latest_stress > 0:
                    add(
                        signal_name,
                        direction,
                        _confidence(55, stress_z, 14, 90),
                        f"Tokyo/Kansai {stress_col.replace('_', ' ')} is {stress_z:.1f}z versus the 60d range.",
                        "Weather-sensitive load risk is elevated relative to recent conditions.",
                        "JEPX area prices may show stronger weather beta if thermal stack is marginal.",
                        "Invalidated by demand nonconfirmation, mild forecast revisions, or strong supply availability.",
                        f"Latest aggregate stress: {latest_stress:.1f}; 60d z-score: {stress_z:.2f}",
                        evidence_date=daily_stress["date"].max(),
                    )

    if {"source_type", "curve_date", "contract_month"}.issubset(curves.columns):
        curves = curves[curves["source_type"].isin(VERIFIED_SOURCES) & curves["curve_date"].between(cutoff - pd.Timedelta(days=4), cutoff) & curves["contract_month"].ge(cutoff.to_period("M").to_timestamp())]
    else:
        curves = curves.iloc[:0]
    steep = calculate_curve_steepness(curves) if {"market", "curve_date", "contract_month", "price"}.issubset(curves.columns) else pd.DataFrame()
    if not steep.empty:
        latest = steep.sort_values("curve_date").groupby("market").tail(1)
        for _, row in latest.iterrows():
            relative_steepness = row["steepness"] / abs(row["front_price"]) * 100 if row["front_price"] else 0
            if relative_steepness > 5:
                add(
                    "Curve contango",
                    f"{row['market']} carry watch",
                    _confidence(55, relative_steepness, 1, 88),
                    f"{row['market']} back month trades {row['steepness']:.2f} above the front.",
                    "Deferred premium suggests positive carry cost for length or storage/seasonal premium.",
                    "Check roll/carry before adding outright exposure.",
                    "Invalidated if prompt tightens or the back-end premium collapses.",
                    f"Back minus front: {row['steepness']:.2f}",
                    evidence_date=row["curve_date"],
                )
            elif relative_steepness < -5:
                add(
                    "Curve backwardation",
                    f"{row['market']} prompt tightness",
                    _confidence(55, relative_steepness, 1, 88),
                    f"{row['market']} front month trades {abs(row['steepness']):.2f} above the back month.",
                    "Nearby premium may reflect tightness or seasonality; it is not an executable carry signal.",
                    "Check tenor coverage, seasonality, liquidity and contract settlement before interpreting calendar spreads.",
                    "Invalidated if front-month premium erodes or supply risk normalizes.",
                    f"Back minus front: {row['steepness']:.2f}",
                    evidence_date=row["curve_date"],
                )


    if not rows:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    return pd.DataFrame(rows, columns=SIGNAL_COLUMNS).sort_values("confidence_score", ascending=False).reset_index(drop=True)
