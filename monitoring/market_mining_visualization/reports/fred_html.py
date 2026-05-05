from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class FredSeriesSummary:
    series_id: str
    start_date: str
    end_date: str
    observations: int
    missing_values: int
    latest_value: float | None
    latest_date: str | None
    svg_path: str


SERIES_GROUPS = [
    ("Liquidity & Policy", ["WALCL", "RRPONTSYD", "M2SL", "DFF"]),
    ("Rates & Risk", ["DGS2", "DGS10", "DFII10", "VIXCLS", "BAMLH0A0HYM2"]),
]

CHART_WIDTH = 640
CHART_HEIGHT = 220


def build_fred_html_report(fred_dir: str | Path, output: str | Path) -> Path:
    """Build a self-contained static HTML report from raw FRED CSV files."""

    fred_path = Path(fred_dir)
    output_path = Path(output)
    summaries = [_summarize_fred_csv(path) for path in sorted(fred_path.glob("*.csv"))]
    if not summaries:
        msg = f"No FRED CSV files found in {fred_path}"
        raise ValueError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_html(summaries), encoding="utf-8")
    return output_path


def _summarize_fred_csv(path: Path) -> FredSeriesSummary:
    data = pd.read_csv(path)
    required_columns = {"date", "series_id", "value", "source"}
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        msg = f"{path} is missing required columns: {sorted(missing_columns)}"
        raise ValueError(msg)

    data = data.sort_values("date").copy()
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    non_missing = data.dropna(subset=["value"])
    latest_row = non_missing.iloc[-1] if not non_missing.empty else None

    series_id = str(data["series_id"].iloc[0])
    return FredSeriesSummary(
        series_id=series_id,
        start_date=str(data["date"].iloc[0]),
        end_date=str(data["date"].iloc[-1]),
        observations=len(data),
        missing_values=int(data["value"].isna().sum()),
        latest_value=None if latest_row is None else float(latest_row["value"]),
        latest_date=None if latest_row is None else str(latest_row["date"]),
        svg_path=_build_svg_path(non_missing["value"].tolist()),
    )


def _build_svg_path(
    values: list[float],
    width: int = CHART_WIDTH,
    height: int = CHART_HEIGHT,
) -> str:
    if not values:
        return ""
    if len(values) == 1:
        y = height / 2
        return f"M 0 {y:.2f} L {width} {y:.2f}"

    lower = min(values)
    upper = max(values)
    value_range = upper - lower
    points: list[str] = []
    for index, value in enumerate(values):
        x = (index / (len(values) - 1)) * width
        if value_range == 0:
            y = height / 2
        else:
            y = height - ((value - lower) / value_range) * height
        points.append(f"{x:.2f} {y:.2f}")
    return "M " + " L ".join(points)


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _render_html(summaries: list[FredSeriesSummary]) -> str:
    sections = _render_sections(summaries)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>market_mining FRED Macro Snapshot</title>
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
      --accent-soft: #102f31;
      --warn: #f0a04b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1360px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 24px;
      padding: 0 0 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 6px;
      color: var(--muted);
    }}
    .count {{
      color: var(--accent);
      background: var(--accent-soft);
      padding: 6px 10px;
      border-radius: 6px;
      white-space: nowrap;
      font-weight: 600;
    }}
    .section {{
      margin-top: 30px;
    }}
    .section-title {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }}
    .section-title h2 {{
      margin: 0;
      font-size: 19px;
      letter-spacing: 0;
    }}
    .section-title span {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));
      gap: 16px;
    }}
    article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }}
    h3 {{
      margin: 0;
      font-size: 17px;
      letter-spacing: 0;
    }}
    .latest {{
      font-size: 24px;
      font-weight: 700;
      color: var(--accent);
      text-align: right;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 12px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .meta strong {{
      display: block;
      color: var(--text);
      font-size: 13px;
      font-weight: 600;
      margin-top: 2px;
      overflow-wrap: anywhere;
    }}
    svg {{
      width: 100%;
      height: 220px;
      margin-top: 16px;
      display: block;
      background: var(--panel-soft);
      border-top: 1px solid #222b35;
      border-bottom: 1px solid #222b35;
    }}
    path {{
      fill: none;
      stroke: var(--accent);
      stroke-width: 2;
      vector-effect: non-scaling-stroke;
    }}
    .missing {{
      color: var(--warn);
    }}
    @media (max-width: 640px) {{
      header {{
        display: block;
      }}
      .count {{
        display: inline-block;
        margin-top: 12px;
      }}
      main {{
        width: min(100vw - 20px, 1180px);
        padding-top: 18px;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      svg {{
        height: 180px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>FRED Macro Snapshot</h1>
        <div class="subtitle">Raw macro series loaded from local market_mining CSV files.</div>
      </div>
      <div class="count">{len(summaries)} series</div>
    </header>
    {sections}
  </main>
</body>
</html>
"""


def _render_sections(summaries: list[FredSeriesSummary]) -> str:
    summary_by_id = {summary.series_id: summary for summary in summaries}
    rendered_sections: list[str] = []
    rendered_ids: set[str] = set()

    for title, series_ids in SERIES_GROUPS:
        group = [summary_by_id[series_id] for series_id in series_ids if series_id in summary_by_id]
        if not group:
            continue
        rendered_ids.update(summary.series_id for summary in group)
        rendered_sections.append(_render_section(title, group))

    remaining = [summary for summary in summaries if summary.series_id not in rendered_ids]
    if remaining:
        rendered_sections.append(_render_section("Other Series", remaining))

    return "\n".join(rendered_sections)


def _render_section(title: str, summaries: list[FredSeriesSummary]) -> str:
    cards = "\n".join(_render_card(summary) for summary in summaries)
    return f"""<section class="section">
      <div class="section-title">
        <h2>{escape(title)}</h2>
        <span>{len(summaries)} series</span>
      </div>
      <div class="grid">
        {cards}
      </div>
    </section>"""


def _render_card(summary: FredSeriesSummary) -> str:
    missing_class = " missing" if summary.missing_values else ""
    return f"""<article>
  <div class="card-head">
    <h3>{escape(summary.series_id)}</h3>
    <div class="latest">{escape(_format_value(summary.latest_value))}</div>
  </div>
  <svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" preserveAspectRatio="none" role="img" aria-label="{escape(summary.series_id)} trend">
    <path d="{escape(summary.svg_path)}"></path>
  </svg>
  <div class="meta">
    <div>Latest date<strong>{escape(summary.latest_date or "n/a")}</strong></div>
    <div>Date range<strong>{escape(summary.start_date)} to {escape(summary.end_date)}</strong></div>
    <div>Observations<strong>{summary.observations:,}</strong></div>
    <div class="{missing_class.strip()}">Missing values<strong>{summary.missing_values:,}</strong></div>
  </div>
</article>"""
