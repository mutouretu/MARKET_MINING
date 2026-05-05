from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.io import to_html


@dataclass
class CompactDashboardInputs:
    snapshot: dict[str, Any]
    scores_daily: pd.DataFrame | None
    score_latest: pd.DataFrame | None
    contributions: pd.DataFrame | None
    regime_latest: pd.DataFrame | None
    regime_daily: pd.DataFrame | None
    features: pd.DataFrame | None
    loaded_files: list[Path]
    missing_files: list[Path]
    warnings: list[str]


def load_compact_dashboard_inputs(analysis_dir: Path) -> CompactDashboardInputs:
    """Load compact dashboard inputs, collecting missing-file warnings."""

    files = {
        "snapshot": analysis_dir / "macro_snapshot_latest.json",
        "scores_daily": analysis_dir / "macro_scores_daily.csv",
        "score_latest": analysis_dir / "macro_score_latest_snapshot.csv",
        "contributions": analysis_dir / "macro_score_contributions_daily.csv",
        "regime_latest": analysis_dir / "market_regime_latest_snapshot.csv",
        "regime_daily": analysis_dir / "market_regime_daily.csv",
        "features": analysis_dir / "macro_features_daily.csv",
    }
    loaded: list[Path] = []
    missing: list[Path] = []
    warnings: list[str] = []

    def read_csv(key: str) -> pd.DataFrame | None:
        path = files[key]
        if not path.exists():
            missing.append(path)
            warnings.append(f"Missing input file: {path}")
            return None
        loaded.append(path)
        return pd.read_csv(path)

    snapshot_path = files["snapshot"]
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        loaded.append(snapshot_path)
    else:
        snapshot = {}
        missing.append(snapshot_path)
        warnings.append(f"Missing input file: {snapshot_path}")

    return CompactDashboardInputs(
        snapshot=snapshot,
        scores_daily=read_csv("scores_daily"),
        score_latest=read_csv("score_latest"),
        contributions=read_csv("contributions"),
        regime_latest=read_csv("regime_latest"),
        regime_daily=read_csv("regime_daily"),
        features=read_csv("features"),
        loaded_files=loaded,
        missing_files=missing,
        warnings=warnings,
    )


def build_compact_dashboard_html(inputs: CompactDashboardInputs) -> str:
    """Build the compact daily-use dashboard HTML."""

    warnings_html = _render_warnings(inputs.warnings)
    state_html = _build_current_state(inputs)
    scores_html = _build_macro_scores(inputs)
    liquidity_html = _build_liquidity_core(inputs)
    transmission_html = _build_btc_transmission(inputs)
    drivers_html = _build_drivers_and_drags(inputs)
    charts_html = _build_compact_charts(inputs)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>market_mining Compact Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0c1116;
      --panel: #151b23;
      --panel-soft: #101720;
      --text: #e6edf3;
      --muted: #8b949e;
      --line: #30363d;
      --accent: #39c5bb;
      --warn: #f0a04b;
      --bad: #ff7b72;
      --good: #7ee787;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1200px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 18px; }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 21px; margin: 30px 0 12px; }}
    h3 {{ font-size: 15px; margin-bottom: 10px; }}
    .subtitle, .muted {{ color: var(--muted); }}
    .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }}
    .panel, .card, .chart-block {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
    }}
    .hero-card strong, .card strong {{
      display: block;
      color: var(--accent);
      font-size: 22px;
      overflow-wrap: anywhere;
    }}
    .hero-card strong {{ font-size: 28px; }}
    .explanation {{ display: grid; gap: 10px; margin-top: 12px; }}
    .row-label {{ display: block; color: var(--muted); font-size: 12px; }}
    .status-strong_positive, .status-positive {{ color: var(--good); }}
    .status-negative, .status-strong_negative {{ color: var(--bad); }}
    .status-neutral {{ color: var(--muted); }}
    .warning {{
      border: 1px solid rgba(240, 160, 75, 0.45);
      background: rgba(240, 160, 75, 0.1);
      color: var(--warn);
      border-radius: 8px;
      padding: 12px 14px;
      margin: 10px 0;
    }}
    .chart-block {{ margin-bottom: 16px; }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      min-width: 820px;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      vertical-align: top;
    }}
    th {{ background: var(--panel-soft); color: var(--muted); }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 1200px); padding-top: 18px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Compact Macro Dashboard</h1>
      <div class="subtitle">Key state, scores, liquidity, transmission, and drivers only.</div>
    </header>
    {warnings_html}
    {state_html}
    {scores_html}
    {liquidity_html}
    {transmission_html}
    {drivers_html}
    {charts_html}
  </main>
</body>
</html>
"""


def write_compact_dashboard(html: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def build_compact_dashboard(analysis_dir: Path, output: Path) -> CompactDashboardInputs:
    inputs = load_compact_dashboard_inputs(analysis_dir)
    html = build_compact_dashboard_html(inputs)
    write_compact_dashboard(html, output)
    return inputs


def _build_current_state(inputs: CompactDashboardInputs) -> str:
    regime = _latest_row(inputs.regime_latest)
    summary = inputs.snapshot.get("regime_summary") or {}
    if not regime and not summary:
        return """<section>
  <h2>Current Market State</h2>
  <div class="warning">Market regime not available. Run Step 7 first.</div>
</section>"""
    values = {**summary, **regime}
    score_values = _latest_score_values(inputs)
    macro_score = score_values.get("macro_liquidity_score")
    cards = [
        ("Current Regime", values.get("regime") or inputs.snapshot.get("key_features", {}).get("market_regime")),
        ("Macro Liquidity Score", macro_score),
        ("Risk Level", values.get("risk_level")),
        ("Primary Driver", values.get("primary_driver")),
        ("Secondary Driver", values.get("secondary_driver")),
    ]
    return f"""<section>
  <h2>Current Market State</h2>
  <div class="grid">{''.join(_card(label, value, hero=True) for label, value in cards)}</div>
  <div class="panel explanation">
    <div><span class="row-label">date</span>{escape(_format_value(values.get("date")))}</div>
    <div><span class="row-label">allowed_actions</span>{escape(_format_value(values.get("allowed_actions")))}</div>
    <div><span class="row-label">forbidden_actions</span>{escape(_format_value(values.get("forbidden_actions")))}</div>
    <div><span class="row-label">reason</span>{escape(_format_value(values.get("reason")))}</div>
  </div>
</section>"""


def _build_macro_scores(inputs: CompactDashboardInputs) -> str:
    values = _latest_score_values(inputs)
    keys = [
        "macro_liquidity_score",
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "score_coverage_ratio",
    ]
    cards = []
    for key in keys:
        value = values.get(key)
        status = _score_status(value) if key != "score_coverage_ratio" else "neutral"
        cards.append(_score_card(key, value, status))
    return f"""<section>
  <h2>Macro Scores</h2>
  <div class="muted">Scores are explanatory state indicators, not trading signals.</div>
  <div class="grid" style="margin-top: 12px;">{''.join(cards)}</div>
</section>"""


def _build_liquidity_core(inputs: CompactDashboardInputs) -> str:
    values = _latest_feature_values(inputs)
    keys = [
        "net_liquidity",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "tga_billion_change_30d",
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
    ]
    return f"""<section>
  <h2>Liquidity Core</h2>
  <div class="panel">
    <div>External USD liquidity: net_liquidity = WALCL_BILLION - TGA_BILLION - RRPONTSYD</div>
    <div class="muted">Crypto-native liquidity: total_stablecoin_supply</div>
  </div>
  <div class="grid" style="margin-top: 12px;">{''.join(_card(key, values.get(key)) for key in keys)}</div>
</section>"""


def _build_btc_transmission(inputs: CompactDashboardInputs) -> str:
    values = _latest_feature_values(inputs)
    keys = [
        "btc_price",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_90d",
        "net_liquidity_btc_growth_gap_90d",
        "transmission_phase",
    ]
    return f"""<section>
  <h2>BTC / Transmission</h2>
  <div class="panel">
    <div>Stablecoin supply is treated as a transmission variable, not a standalone leading indicator.</div>
    <div class="muted">Transmission gaps are explanatory variables, not trading signals.</div>
  </div>
  <div class="grid" style="margin-top: 12px;">{''.join(_card(key, values.get(key)) for key in keys)}</div>
</section>"""


def _build_drivers_and_drags(inputs: CompactDashboardInputs) -> str:
    if inputs.contributions is None or inputs.contributions.empty:
        return """<section>
  <h2>Top Drivers and Drags</h2>
  <div class="warning">Score contributions not available. Run Step 6 first.</div>
</section>"""
    data = inputs.contributions.copy()
    if "date" not in data.columns or "weighted_contribution" not in data.columns:
        return """<section>
  <h2>Top Drivers and Drags</h2>
  <div class="warning">Score contributions missing required columns.</div>
</section>"""
    latest_date = data["date"].max()
    latest = data[data["date"] == latest_date].copy()
    if "available" in latest.columns:
        latest = latest[latest["available"].astype(str).str.lower().isin({"true", "1"})]
    latest["weighted_contribution"] = pd.to_numeric(
        latest["weighted_contribution"], errors="coerce"
    )
    columns = [
        "date",
        "score_name",
        "feature",
        "feature_value",
        "feature_score",
        "weight",
        "weighted_contribution",
    ]
    supports = latest.sort_values("weighted_contribution", ascending=False).head(5)
    drags = latest.sort_values("weighted_contribution", ascending=True).head(5)
    return f"""<section>
  <h2>Top Drivers and Drags</h2>
  <h3>Top Supports</h3>
  {_table(supports, columns)}
  <h3 style="margin-top: 16px;">Top Drags</h3>
  {_table(drags, columns)}
</section>"""


def _build_compact_charts(inputs: CompactDashboardInputs) -> str:
    charts: list[str] = []
    include_plotlyjs: bool | str = True
    specs = [
        (
            "Macro Liquidity Score - Last 180 Days",
            inputs.scores_daily,
            ["macro_liquidity_score"],
        ),
        (
            "Subscores - Last 180 Days",
            inputs.scores_daily,
            [
                "fed_policy_score",
                "usd_liquidity_score",
                "rates_pressure_score",
                "risk_appetite_score",
                "stablecoin_liquidity_score",
                "btc_market_score",
            ],
        ),
        (
            "Liquidity Core - Last 180 Days",
            inputs.features,
            ["net_liquidity_change_90d", "total_stablecoin_supply_change_90d"],
        ),
    ]
    for title, data, columns in specs:
        chart_html, include_plotlyjs = _chart(title, data, columns, include_plotlyjs)
        charts.append(chart_html)
    return f"""<section>
  <h2>Compact Charts</h2>
  {''.join(charts)}
</section>"""


def _chart(
    title: str,
    data: pd.DataFrame | None,
    columns: list[str],
    include_plotlyjs: bool | str,
) -> tuple[str, bool | str]:
    if data is None or data.empty:
        return _warning_block(title, "Input data not available."), include_plotlyjs
    if "date" not in data.columns:
        return _warning_block(title, "Missing columns: date"), include_plotlyjs
    missing = [column for column in columns if column not in data.columns]
    if missing:
        return _warning_block(title, f"Missing columns: {', '.join(missing)}"), include_plotlyjs
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").tail(180)
    figure = go.Figure()
    for column in columns:
        figure.add_trace(
            go.Scatter(
                x=frame["date"],
                y=pd.to_numeric(frame[column], errors="coerce"),
                mode="lines",
                name=column,
            )
        )
    figure.update_layout(
        title=title,
        height=360,
        template="plotly_dark",
        hovermode="x unified",
        margin={"l": 48, "r": 24, "t": 58, "b": 42},
        paper_bgcolor="#151b23",
        plot_bgcolor="#101720",
        font={"color": "#e6edf3"},
        legend={"orientation": "h", "y": -0.18},
    )
    html = to_html(
        figure,
        include_plotlyjs=include_plotlyjs,
        full_html=False,
        config={"displaylogo": False, "responsive": True},
    )
    return f"""<section class="chart-block">
  <h3>{escape(title)}</h3>
  {html}
</section>""", False


def _latest_score_values(inputs: CompactDashboardInputs) -> dict[str, Any]:
    values = {}
    values.update(inputs.snapshot.get("key_features") or {})
    values.update(inputs.snapshot.get("score_summary") or {})
    values.update(_latest_row(inputs.score_latest))
    return values


def _latest_feature_values(inputs: CompactDashboardInputs) -> dict[str, Any]:
    values = {}
    values.update(inputs.snapshot.get("key_features") or {})
    values.update(_latest_row(inputs.features))
    return values


def _latest_row(data: pd.DataFrame | None) -> dict[str, Any]:
    if data is None or data.empty:
        return {}
    frame = data.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values("date")
    return frame.iloc[-1].to_dict()


def _score_status(value: Any) -> str:
    if value is None or pd.isna(value):
        return "neutral"
    score = float(value)
    if score >= 70:
        return "strong_positive"
    if score >= 55:
        return "positive"
    if score >= 45:
        return "neutral"
    if score >= 30:
        return "negative"
    return "strong_negative"


def _score_card(label: str, value: Any, status: str) -> str:
    return f"""<article class="card">
  <span class="muted">{escape(label)}</span>
  <strong>{escape(_format_value(value))}</strong>
  <span class="status-{escape(status)}">{escape(status)}</span>
</article>"""


def _card(label: str, value: Any, hero: bool = False) -> str:
    klass = "card hero-card" if hero else "card"
    return f"""<article class="{klass}">
  <span class="muted">{escape(label)}</span>
  <strong>{escape(_format_value(value))}</strong>
</article>"""


def _table(data: pd.DataFrame, columns: list[str]) -> str:
    existing = [column for column in columns if column in data.columns]
    if not existing:
        return '<div class="warning">No table columns available.</div>'
    header = "".join(f"<th>{escape(column)}</th>" for column in existing)
    rows = []
    for _, row in data[existing].iterrows():
        cells = "".join(f"<td>{escape(_format_value(row[column]))}</td>" for column in existing)
        rows.append(f"<tr>{cells}</tr>")
    return f"""<div class="table-wrap">
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def _render_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    return "".join(f'<div class="warning">{escape(warning)}</div>' for warning in warnings)


def _warning_block(title: str, warning: str) -> str:
    return f"""<section class="chart-block">
  <h3>{escape(title)}</h3>
  <div class="warning">{escape(warning)}</div>
</section>"""


def _format_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return value
    try:
        return f"{float(value):,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)
