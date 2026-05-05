from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.io import to_html

NO_TGA_WARNING = "USD liquidity proxy excludes TGA and should not be treated as full net liquidity."
NET_LIQUIDITY_NOTE = "Net Liquidity = WALCL_BILLION - TGA_BILLION - RRPONTSYD."
PROXY_COMPARISON_NOTE = "Proxy without TGA is retained for comparison only."

KEY_CHARTS = [
    {
        "title": "Net Liquidity",
        "columns": ["net_liquidity"],
        "description": "Computed as WALCL_BILLION - TGA_BILLION - RRPONTSYD.",
    },
    {
        "title": "Net Liquidity Change",
        "columns": ["net_liquidity_change_30d", "net_liquidity_change_90d"],
        "description": "",
    },
    {
        "title": "TGA Balance",
        "columns": ["tga_billion"],
        "description": (
            "Higher TGA can absorb liquidity from markets; lower TGA can release liquidity."
        ),
    },
    {
        "title": "TGA Change",
        "columns": ["tga_billion_change_30d", "tga_billion_change_90d"],
        "description": "",
    },
    {
        "title": "USD Liquidity Proxy without TGA",
        "columns": ["usd_liquidity_proxy_no_tga"],
        "description": "Retained for comparison. This excludes TGA.",
    },
    {
        "title": "10Y Real Yield",
        "columns": ["DFII10"],
        "description": "",
    },
    {
        "title": "Risk Appetite: VIX and High Yield OAS",
        "columns": ["VIXCLS", "BAMLH0A0HYM2"],
        "description": "",
    },
    {
        "title": "Risk Appetite 30d Change",
        "columns": ["VIXCLS_change_30d", "BAMLH0A0HYM2_change_30d"],
        "description": "",
    },
]

CRYPTO_LIQUIDITY_CHARTS = [
    {
        "title": "Total Stablecoin Supply",
        "columns": ["total_stablecoin_supply"],
        "description": "Proxy for crypto-native dollar liquidity.",
    },
    {
        "title": "Stablecoin Supply Change",
        "columns": [
            "total_stablecoin_supply_change_30d",
            "total_stablecoin_supply_change_90d",
        ],
        "description": "",
    },
    {
        "title": "USDT / USDC Supply",
        "columns": ["usdt_supply", "usdc_supply"],
        "description": "",
    },
    {
        "title": "USDT / USDC Dominance",
        "columns": ["usdt_dominance", "usdc_dominance"],
        "description": "",
    },
]

TRANSMISSION_CHARTS = [
    {"title": "BTC Price", "columns": ["btc_price"], "description": ""},
    {
        "title": "Stablecoin / BTC Market Cap",
        "columns": ["stablecoin_to_btc_mcap"],
        "description": "Measures crypto-native dollar liquidity relative to BTC market cap.",
    },
    {
        "title": "Liquidity Transmission Gap",
        "columns": ["liquidity_transmission_gap_30d", "liquidity_transmission_gap_90d"],
        "description": "Net liquidity growth minus stablecoin supply growth.",
    },
    {
        "title": "Stablecoin Growth vs BTC Return",
        "columns": ["stablecoin_supply_growth_30d", "btc_return_30d"],
        "description": "",
    },
    {
        "title": "Net Liquidity Growth vs BTC Return",
        "columns": ["net_liquidity_growth_90d", "btc_return_90d"],
        "description": "",
    },
]

SCORE_CHARTS = [
    {
        "title": "Macro Liquidity Score",
        "columns": ["macro_liquidity_score"],
        "description": "Rule-based composite score. 50 is neutral; higher is more favorable.",
    },
    {
        "title": "Subscores",
        "columns": [
            "fed_policy_score",
            "usd_liquidity_score",
            "rates_pressure_score",
            "risk_appetite_score",
            "stablecoin_liquidity_score",
            "btc_market_score",
        ],
        "description": "",
    },
    {
        "title": "USD Liquidity Score vs Net Liquidity",
        "columns": ["usd_liquidity_score", "net_liquidity"],
        "description": "",
    },
    {
        "title": "Rates / Risk Appetite Scores",
        "columns": ["rates_pressure_score", "risk_appetite_score"],
        "description": "",
    },
]

REGIME_CHARTS = [
    {
        "title": "Macro Liquidity Score with Regime",
        "columns": ["macro_liquidity_score"],
        "description": "Read alongside the Market Regime Timeline table.",
    },
    {
        "title": "Subscores by Regime",
        "columns": [
            "usd_liquidity_score",
            "risk_appetite_score",
            "stablecoin_liquidity_score",
            "btc_market_score",
        ],
        "description": "",
    },
]

GROUP_ORDER = ["fed_policy", "usd_liquidity", "rates", "risk_appetite", "other"]


def load_analysis_outputs(
    analysis_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame | None]:
    """Load analysis outputs required by the static dashboard."""

    summary_path = analysis_dir / "fred_series_summary.csv"
    features_path = analysis_dir / "macro_features_daily.csv"
    snapshot_path = analysis_dir / "macro_snapshot_latest.json"

    summary_df = pd.read_csv(summary_path)
    features_df = pd.read_csv(features_path)
    scores_path = analysis_dir / "macro_scores_daily.csv"
    if scores_path.exists():
        scores_df = pd.read_csv(scores_path)
        if "date" in scores_df.columns:
            score_columns = [column for column in scores_df.columns if column != "date"]
            features_df = features_df.drop(columns=score_columns, errors="ignore")
            features_df = features_df.merge(scores_df, on="date", how="outer")
    regime_path = analysis_dir / "market_regime_daily.csv"
    if regime_path.exists():
        regime_df = pd.read_csv(regime_path)
        if "date" in regime_df.columns:
            regime_columns = [
                column
                for column in [
                    "date",
                    "regime",
                    "regime_score",
                    "regime_confidence",
                    "risk_level",
                    "primary_driver",
                    "secondary_driver",
                    "allowed_actions",
                    "forbidden_actions",
                    "reason",
                ]
                if column in regime_df.columns
            ]
            features_df = features_df.drop(
                columns=[column for column in regime_columns if column != "date"],
                errors="ignore",
            )
            features_df = features_df.merge(regime_df[regime_columns], on="date", how="outer")
    transitions_path = analysis_dir / "market_regime_transitions.csv"
    transitions_df = pd.read_csv(transitions_path) if transitions_path.exists() else None
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return summary_df, features_df, snapshot, transitions_df


def build_summary_cards(summary_df: pd.DataFrame) -> str:
    """Build grouped latest-status cards from the series summary table."""

    if summary_df.empty:
        return '<div class="warning">No summary rows available.</div>'

    summary = summary_df.copy()
    summary["group"] = summary["group"].fillna("other")
    sections: list[str] = []
    for group in GROUP_ORDER + sorted(set(summary["group"]) - set(GROUP_ORDER)):
        group_rows = summary[summary["group"] == group]
        if group_rows.empty:
            continue
        cards = "\n".join(_render_metric_card(row) for _, row in group_rows.iterrows())
        sections.append(
            f"""<section class="card-group">
  <h3>{escape(group)}</h3>
  <div class="card-grid">{cards}</div>
</section>"""
        )
    return "\n".join(sections)


def build_key_charts(features_df: pd.DataFrame) -> tuple[str, list[str]]:
    """Build Plotly key chart blocks. Missing columns become warning blocks."""

    return _build_chart_blocks(features_df, KEY_CHARTS)


def build_crypto_liquidity(features_df: pd.DataFrame, snapshot: dict[str, Any]) -> tuple[str, list[str]]:
    """Build crypto-native liquidity snapshot and stablecoin chart blocks."""

    stablecoin_cards = _build_stablecoin_snapshot_cards(snapshot)
    chart_blocks, warnings = _build_chart_blocks(features_df, CRYPTO_LIQUIDITY_CHARTS)
    html = f"""<section>
      <h2>Crypto Liquidity</h2>
      <div class="panel liquidity-note">
        <div>Stablecoin supply is used as a proxy for crypto-native dollar liquidity.</div>
      </div>
      <div class="snapshot-grid">{stablecoin_cards}</div>
      {chart_blocks}
    </section>"""
    return html, warnings


def build_transmission_divergence(
    features_df: pd.DataFrame,
    snapshot: dict[str, Any],
) -> tuple[str, list[str]]:
    """Build transmission/divergence snapshot and chart blocks."""

    cards = _build_transmission_snapshot_cards(snapshot)
    chart_blocks, warnings = _build_chart_blocks(features_df, TRANSMISSION_CHARTS)
    html = f"""<section>
      <h2>Transmission / Divergence</h2>
      <div class="panel liquidity-note">
        <div>Stablecoin supply is treated as a transmission variable, not a standalone trading signal.</div>
      </div>
      <div class="snapshot-grid">{cards}</div>
      {chart_blocks}
    </section>"""
    return html, warnings


def build_macro_scores_section(
    features_df: pd.DataFrame,
    snapshot: dict[str, Any],
) -> tuple[str, list[str]]:
    """Build score snapshot and chart blocks."""

    score_fields = {
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "macro_liquidity_score",
        "score_coverage_ratio",
    }
    has_score_data = bool(score_fields & set(features_df.columns)) or bool(
        snapshot.get("score_summary")
    )
    if not has_score_data:
        return "", []

    cards = _build_score_snapshot_cards(snapshot)
    chart_blocks, warnings = _build_chart_blocks(features_df, SCORE_CHARTS)
    html = f"""<section>
      <h2>Macro Scores</h2>
      <div class="panel liquidity-note">
        <div>Macro scoring v0.1 is rule-based and explanatory, not a trading signal.</div>
      </div>
      <div class="snapshot-grid">{cards}</div>
      {chart_blocks}
    </section>"""
    return html, warnings


def build_market_regime_section(
    features_df: pd.DataFrame,
    snapshot: dict[str, Any],
    transitions_df: pd.DataFrame | None = None,
) -> tuple[str, list[str]]:
    """Build market regime cards, explanation, charts, and transition table."""

    has_regime_data = "regime" in features_df.columns or bool(snapshot.get("regime_summary"))
    if not has_regime_data:
        return "", []

    cards = _build_regime_snapshot_cards(snapshot)
    explanation = _build_regime_explanation(snapshot)
    timeline = _build_regime_timeline(features_df)
    chart_blocks, warnings = _build_chart_blocks(features_df, REGIME_CHARTS)
    transitions = _build_regime_transition_table(transitions_df)
    html = f"""<section>
      <h2>Market Regime</h2>
      <div class="panel liquidity-note">
        <div>Market regime v0.1 is rule-based and explanatory, not a trading signal.</div>
      </div>
      <div class="snapshot-grid">{cards}</div>
      {explanation}
      <section class="chart-block">
        <h3>Market Regime Timeline</h3>
        {timeline}
      </section>
      {chart_blocks}
      <section>
        <h3>Recent Regime Transitions</h3>
        {transitions}
      </section>
    </section>"""
    return html, warnings


def _build_chart_blocks(
    features_df: pd.DataFrame,
    chart_specs: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Build Plotly chart blocks. Missing columns become warning blocks."""

    warnings: list[str] = []
    chart_blocks: list[str] = []
    if "date" not in features_df.columns:
        return '<div class="warning">Missing columns: date</div>', ["Missing columns: date"]

    features = features_df.copy()
    features["date"] = pd.to_datetime(features["date"], errors="coerce")
    include_plotlyjs: bool | str = True
    for chart in chart_specs:
        title = chart["title"]
        columns = chart["columns"]
        missing_columns = [column for column in columns if column not in features.columns]
        if missing_columns:
            warning = f"Missing columns: {', '.join(missing_columns)}"
            warnings.append(f"{title}: {warning}")
            chart_blocks.append(_render_warning_chart(title, warning, chart["description"]))
            continue

        figure = go.Figure()
        for column in columns:
            figure.add_trace(
                go.Scatter(
                    x=features["date"],
                    y=pd.to_numeric(features[column], errors="coerce"),
                    mode="lines",
                    name=column,
                )
            )
        figure.update_layout(
            title=title,
            height=380,
            template="plotly_dark",
            hovermode="x unified",
            margin={"l": 48, "r": 24, "t": 58, "b": 42},
            paper_bgcolor="#151b23",
            plot_bgcolor="#101720",
            font={"color": "#e6edf3"},
            legend={"orientation": "h", "y": -0.18},
        )
        chart_html = to_html(
            figure,
            include_plotlyjs=include_plotlyjs,
            full_html=False,
            config={"displaylogo": False, "responsive": True},
        )
        include_plotlyjs = False
        chart_blocks.append(
            f"""<section class="chart-block">
  <h3>{escape(title)}</h3>
  {_render_chart_description(chart["description"])}
  {chart_html}
</section>"""
        )
    return "\n".join(chart_blocks), warnings


def build_data_inventory(summary_df: pd.DataFrame) -> str:
    """Build data inventory table for freshness and quality inspection."""

    columns = [
        "series_id",
        "label",
        "group",
        "first_date",
        "last_date",
        "observations",
        "missing_values_raw",
        "missing_values_after_ffill",
        "unit",
        "bullish_when",
    ]
    missing = [column for column in columns if column not in summary_df.columns]
    if missing:
        return f'<div class="warning">Missing columns: {escape(", ".join(missing))}</div>'

    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    rows = []
    for _, row in summary_df[columns].iterrows():
        cells = "".join(f"<td>{escape(_format_cell(row[column]))}</td>" for column in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"""<div class="freshness-note">
  Freshness note: lower-frequency series may have an older last_date than the dashboard latest_date.
</div>
<div class="table-wrap">
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_dashboard_html(
    summary_df: pd.DataFrame,
    features_df: pd.DataFrame,
    snapshot: dict[str, Any],
    transitions_df: pd.DataFrame | None = None,
) -> tuple[str, list[str]]:
    """Build the complete static dashboard HTML."""

    key_charts_html, chart_warnings = build_key_charts(features_df)
    cards_html = build_summary_cards(summary_df)
    inventory_html = build_data_inventory(summary_df)
    has_net_liquidity = _has_net_liquidity(snapshot, features_df)
    snapshot_html = _build_snapshot_html(snapshot, has_net_liquidity)
    liquidity_notice = _build_liquidity_notice(has_net_liquidity)
    crypto_html, crypto_warnings = build_crypto_liquidity(features_df, snapshot)
    transmission_html, transmission_warnings = build_transmission_divergence(features_df, snapshot)
    scores_html, score_warnings = build_macro_scores_section(features_df, snapshot)
    regime_html, regime_warnings = build_market_regime_section(
        features_df, snapshot, transitions_df
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>market_mining Static Macro Dashboard</title>
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
      width: min(1400px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1, h2, h3 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 22px; margin-top: 34px; margin-bottom: 14px; }}
    h3 {{ font-size: 16px; margin-bottom: 10px; }}
    .subtitle, .muted, .freshness-note {{
      color: var(--muted);
    }}
    .snapshot-grid, .card-grid {{
      display: grid;
      gap: 14px;
    }}
    .snapshot-grid {{
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      margin-top: 14px;
    }}
    .card-grid {{
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}
    .panel, .metric-card, .chart-block {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric-card strong, .feature-value {{
      display: block;
      font-size: 22px;
      color: var(--accent);
      margin-top: 2px;
    }}
    .metric-meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 12px;
      margin-top: 12px;
      font-size: 12px;
      color: var(--muted);
    }}
    .metric-meta b {{
      display: block;
      color: var(--text);
      overflow-wrap: anywhere;
    }}
    .card-group {{
      margin-top: 18px;
    }}
    .warning {{
      border: 1px solid rgba(240, 160, 75, 0.45);
      background: rgba(240, 160, 75, 0.1);
      color: var(--warn);
      border-radius: 8px;
      padding: 12px 14px;
      margin: 10px 0;
    }}
    .no-tga {{
      border-color: rgba(255, 123, 114, 0.55);
      color: var(--bad);
      font-weight: 700;
    }}
    .positive_for_btc, .improving {{ color: var(--good); }}
    .negative_for_btc, .deteriorating {{ color: var(--bad); }}
    .neutral {{ color: var(--muted); }}
    .chart-block {{
      margin-bottom: 18px;
    }}
    .chart-description {{
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: var(--panel-soft);
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 1400px); padding-top: 18px; }}
      .metric-meta {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Static Macro Dashboard</h1>
      <div class="subtitle">Visualization of market_mining analysis outputs.</div>
    </header>

    <section>
      <h2>Macro Snapshot</h2>
      {liquidity_notice}
      {snapshot_html}
      {cards_html}
    </section>

    <section>
      <h2>Key Charts</h2>
      {key_charts_html}
    </section>

    {crypto_html}

    {transmission_html}

    {scores_html}

    {regime_html}

    <section>
      <h2>Data Inventory</h2>
      {inventory_html}
    </section>
  </main>
</body>
</html>
"""
    return (
        html,
        chart_warnings
        + crypto_warnings
        + transmission_warnings
        + score_warnings
        + regime_warnings,
    )


def write_dashboard(html: str, output: Path) -> None:
    """Write dashboard HTML to disk."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def build_dashboard(analysis_dir: Path, output: Path) -> list[str]:
    """Build and write a static dashboard from analysis outputs."""

    summary_df, features_df, snapshot, transitions_df = load_analysis_outputs(analysis_dir)
    html, warnings = build_dashboard_html(summary_df, features_df, snapshot, transitions_df)
    write_dashboard(html, output)
    return warnings


def _build_snapshot_html(snapshot: dict[str, Any], has_net_liquidity: bool) -> str:
    latest_date = escape(str(snapshot.get("latest_date", "n/a")))
    series_count = escape(str(snapshot.get("series_count", "n/a")))
    notes = snapshot.get("notes") or []
    key_features = snapshot.get("key_features") or {}

    ordered_keys = _ordered_snapshot_keys(key_features)
    feature_cards = "".join(
        f"""<div class="panel">
  <span class="muted">{escape(key)}</span>
  <span class="feature-value">{escape(_format_value(value))}</span>
</div>"""
        for key, value in ((key, key_features[key]) for key in ordered_keys)
    )
    visible_notes = _visible_snapshot_notes(notes, has_net_liquidity)
    notes_html = "".join(f"<li>{escape(str(note))}</li>" for note in visible_notes)
    return f"""<div class="snapshot-grid">
  <div class="panel"><span class="muted">latest_date</span><span class="feature-value">{latest_date}</span></div>
  <div class="panel"><span class="muted">series_count</span><span class="feature-value">{series_count}</span></div>
  {feature_cards}
</div>
<div class="panel" style="margin-top: 14px;">
  <h3>Notes</h3>
  <ul>{notes_html}</ul>
</div>"""


def _has_net_liquidity(snapshot: dict[str, Any], features_df: pd.DataFrame) -> bool:
    key_features = snapshot.get("key_features") or {}
    if key_features.get("net_liquidity") is not None:
        return True
    return "net_liquidity" in features_df.columns and not features_df["net_liquidity"].isna().all()


def _build_liquidity_notice(has_net_liquidity: bool) -> str:
    if has_net_liquidity:
        return f"""<div class="panel liquidity-note">
  <div>{NET_LIQUIDITY_NOTE}</div>
  <div class="muted">{PROXY_COMPARISON_NOTE}</div>
</div>"""
    return f'<div class="warning no-tga">{NO_TGA_WARNING}</div>'


def _ordered_snapshot_keys(key_features: dict[str, Any]) -> list[str]:
    preferred = [
        "net_liquidity",
        "net_liquidity_change_30d",
        "net_liquidity_change_90d",
        "tga_billion",
        "tga_billion_change_30d",
        "tga_billion_change_90d",
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
        "usdt_supply",
        "usdc_supply",
        "usdt_dominance",
        "usdc_dominance",
        "btc_price",
        "btc_market_cap",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_30d",
        "stablecoin_btc_growth_gap_90d",
        "transmission_phase",
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "macro_liquidity_score",
        "score_coverage_ratio",
        "market_regime",
        "regime_score",
        "regime_confidence",
        "risk_level",
        "primary_driver",
        "secondary_driver",
        "usd_liquidity_proxy_no_tga",
        "usd_liquidity_proxy_no_tga_change_30d",
        "yield_curve_10y_2y",
        "breakeven_10y_proxy",
    ]
    ordered = [key for key in preferred if key in key_features]
    ordered.extend(key for key in key_features if key not in ordered)
    return ordered


def _visible_snapshot_notes(notes: list[Any], has_net_liquidity: bool) -> list[Any]:
    if not has_net_liquidity:
        return notes
    return [
        note
        for note in notes
        if "should not be treated as full net liquidity" not in str(note)
    ]


def _build_stablecoin_snapshot_cards(snapshot: dict[str, Any]) -> str:
    key_features = snapshot.get("key_features") or {}
    keys = [
        "total_stablecoin_supply",
        "total_stablecoin_supply_change_30d",
        "total_stablecoin_supply_change_90d",
        "usdt_supply",
        "usdc_supply",
        "usdt_dominance",
        "usdc_dominance",
    ]
    cards = []
    for key in keys:
        if key not in key_features:
            continue
        cards.append(
            f"""<div class="panel">
  <span class="muted">{escape(key)}</span>
  <span class="feature-value">{escape(_format_value(key_features.get(key)))}</span>
</div>"""
        )
    if not cards:
        return '<div class="warning">Missing stablecoin snapshot fields.</div>'
    return "".join(cards)


def _build_transmission_snapshot_cards(snapshot: dict[str, Any]) -> str:
    key_features = snapshot.get("key_features") or {}
    keys = [
        "btc_price",
        "btc_market_cap",
        "btc_return_30d",
        "btc_return_90d",
        "stablecoin_to_btc_mcap",
        "btc_to_stablecoin_ratio",
        "liquidity_transmission_gap_30d",
        "liquidity_transmission_gap_90d",
        "stablecoin_btc_growth_gap_30d",
        "stablecoin_btc_growth_gap_90d",
        "transmission_phase",
    ]
    cards = []
    for key in keys:
        if key not in key_features:
            continue
        cards.append(
            f"""<div class="panel">
  <span class="muted">{escape(key)}</span>
  <span class="feature-value">{escape(_format_value(key_features.get(key)))}</span>
</div>"""
        )
    if not cards:
        return '<div class="warning">Missing transmission snapshot fields.</div>'
    return "".join(cards)


def _build_score_snapshot_cards(snapshot: dict[str, Any]) -> str:
    key_features = snapshot.get("key_features") or {}
    score_summary = snapshot.get("score_summary") or {}
    values = {**key_features, **score_summary}
    keys = [
        "fed_policy_score",
        "usd_liquidity_score",
        "rates_pressure_score",
        "risk_appetite_score",
        "stablecoin_liquidity_score",
        "btc_market_score",
        "macro_liquidity_score",
        "score_coverage_ratio",
    ]
    cards = []
    for key in keys:
        if key not in values:
            continue
        cards.append(
            f"""<div class="panel">
  <span class="muted">{escape(key)}</span>
  <span class="feature-value">{escape(_format_value(values.get(key)))}</span>
</div>"""
        )
    if not cards:
        return '<div class="warning">Missing macro score snapshot fields.</div>'
    return "".join(cards)


def _build_regime_snapshot_cards(snapshot: dict[str, Any]) -> str:
    key_features = snapshot.get("key_features") or {}
    regime_summary = snapshot.get("regime_summary") or {}
    values = {**key_features, **regime_summary}
    keys = [
        "market_regime",
        "regime",
        "regime_score",
        "regime_confidence",
        "risk_level",
        "primary_driver",
        "secondary_driver",
    ]
    cards = []
    seen = set()
    for key in keys:
        if key in seen or key not in values:
            continue
        seen.add(key)
        cards.append(
            f"""<div class="panel">
  <span class="muted">{escape(key)}</span>
  <span class="feature-value">{escape(_format_value(values.get(key)))}</span>
</div>"""
        )
    if not cards:
        return '<div class="warning">Missing market regime snapshot fields.</div>'
    return "".join(cards)


def _build_regime_explanation(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("regime_summary") or {}
    if not summary:
        return '<div class="warning">Missing regime_summary.</div>'
    rows = [
        ("allowed_actions", summary.get("allowed_actions")),
        ("forbidden_actions", summary.get("forbidden_actions")),
        ("reason", summary.get("reason")),
    ]
    body = "".join(
        f"""<div class="metric-meta-row">
  <span class="muted">{escape(label)}</span>
  <b>{escape(_format_cell(value))}</b>
</div>"""
        for label, value in rows
    )
    return f"""<div class="panel" style="margin-top: 14px;">
  <h3>Regime Explanation</h3>
  {body}
</div>"""


def _build_regime_timeline(features_df: pd.DataFrame) -> str:
    columns = ["date", "regime", "regime_score", "regime_confidence", "risk_level"]
    if not set(columns).issubset(features_df.columns):
        missing = [column for column in columns if column not in features_df.columns]
        return f'<div class="warning">Missing columns: {escape(", ".join(missing))}</div>'
    data = features_df[columns].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date").tail(60)
    return _render_table(data, columns)


def _build_regime_transition_table(transitions_df: pd.DataFrame | None) -> str:
    if transitions_df is None or transitions_df.empty:
        return '<div class="warning">No regime transitions available.</div>'
    columns = [
        "date",
        "previous_regime",
        "regime",
        "regime_score",
        "regime_confidence",
        "primary_driver",
        "risk_level",
    ]
    missing = [column for column in columns if column not in transitions_df.columns]
    if missing:
        return f'<div class="warning">Missing columns: {escape(", ".join(missing))}</div>'
    data = transitions_df[columns].tail(20)
    return _render_table(data, columns)


def _render_table(data: pd.DataFrame, columns: list[str]) -> str:
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    rows = []
    for _, row in data.iterrows():
        cells = "".join(f"<td>{escape(_format_cell(row[column]))}</td>" for column in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"""<div class="table-wrap">
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def _render_metric_card(row: pd.Series) -> str:
    label = escape(_format_cell(row.get("label")))
    series_id = escape(_format_cell(row.get("series_id")))
    group = escape(_format_cell(row.get("group")))
    latest_value = escape(_format_value(row.get("latest_value")))
    implication = escape(_format_cell(row.get("btc_implication")))
    status = escape(_format_cell(row.get("status")))
    return f"""<article class="metric-card">
  <div class="muted">{series_id} · {group}</div>
  <strong>{label}</strong>
  <div class="metric-meta">
    <div>latest_value<b>{latest_value}</b></div>
    <div>last_date<b>{escape(_format_cell(row.get("last_date")))}</b></div>
    <div>change_30d<b>{escape(_format_value(row.get("change_30d")))}</b></div>
    <div>change_90d<b>{escape(_format_value(row.get("change_90d")))}</b></div>
    <div>pct_change_90d<b>{escape(_format_value(row.get("pct_change_90d")))}</b></div>
    <div>zscore_252d<b>{escape(_format_value(row.get("zscore_252d")))}</b></div>
    <div>btc_implication<b class="{implication}">{implication}</b></div>
    <div>status<b class="{status}">{status}</b></div>
  </div>
</article>"""


def _render_warning_chart(title: str, warning: str, description: str) -> str:
    return f"""<section class="chart-block">
  <h3>{escape(title)}</h3>
  {_render_chart_description(description)}
  <div class="warning">{escape(warning)}</div>
</section>"""


def _render_chart_description(description: str) -> str:
    if not description:
        return ""
    return f'<div class="chart-description">{escape(description)}</div>'


def _format_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if isinstance(value, str):
        return value
    return f"{float(value):,.4f}".rstrip("0").rstrip(".")


def _format_cell(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)
