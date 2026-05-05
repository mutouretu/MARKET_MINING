from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import typer
import yaml
from rich.console import Console

from market_mining import __version__
from market_mining.config import Config, load_config
from market_mining_analysis.feature_eligibility import run_feature_eligibility_review
from market_mining_analysis.fred_macro import run_fred_macro_analysis
from market_mining_analysis.macro_feature_consolidation import (
    MacroFeatureConsolidationError,
    consolidate_macro_features,
)
from market_mining_analysis.regime import RegimeError, run_market_regime_update
from market_mining_analysis.scoring import run_macro_scoring
from market_mining_analysis.stablecoin_liquidity import (
    StablecoinLiquidityError,
    run_stablecoin_liquidity_update,
)
from market_mining_analysis.transmission_features import (
    TransmissionFeatureError,
    run_transmission_update,
)
from market_mining_analysis.usd_liquidity import UsdLiquidityError, run_usd_liquidity_update
from market_mining_data_mining.coingecko_btc import (
    CoinGeckoBtcError,
    fetch_btc_market_chart,
    load_json as load_btc_json,
    parse_btc_market_chart,
    save_btc_market_daily,
    save_json as save_btc_json,
)
from market_mining_data_mining.defillama_stablecoins import (
    DeFiLlamaStablecoinError,
    build_stablecoin_current_summary,
    fetch_stablecoin_charts_all,
    fetch_stablecoins_current,
    load_json,
    parse_stablecoin_charts_all,
    parse_stablecoins_current,
    save_json,
)
from market_mining_data_mining.sources.fred import (
    FredApiError,
    fetch_fred_batch_to_csv,
    fetch_fred_series_to_csv,
)
from market_mining_data_mining.treasury_tga import (
    TreasuryTgaError,
    build_tga_daily,
    fetch_tga_operating_cash_balance,
    inspect_tga_account_types,
    save_tga_account_type_summary,
    save_tga_daily,
    save_tga_raw,
    validate_tga_daily,
)
from market_mining_visualization.build_compact_dashboard import build_compact_dashboard
from market_mining_visualization.build_dashboard import build_dashboard
from market_mining_visualization.reports.fred_html import build_fred_html_report

app = typer.Typer(help="market_mining command line interface.")
console = Console()


def _config_to_dict(config: Config) -> dict[str, Any]:
    if hasattr(config, "model_dump"):
        return config.model_dump()
    return config.dict()


@app.command()
def version() -> None:
    """Print the package version."""

    console.print(__version__)


@app.command("show-config")
def show_config(
    config: Path = typer.Option(
        Path("data_mining/configs/default.yaml"),
        "--config",
        "-c",
        help="Path to the YAML configuration file.",
    ),
) -> None:
    """Print the loaded configuration."""

    loaded_config = load_config(config)
    console.print(yaml.safe_dump(_config_to_dict(loaded_config), sort_keys=False))


@app.command("fetch-fred")
def fetch_fred(
    series: str = typer.Option(..., "--series", "-s", help="FRED series ID."),
    start: str | None = typer.Option(None, "--start", help="Observation start date, YYYY-MM-DD."),
    end: str | None = typer.Option(None, "--end", help="Observation end date, YYYY-MM-DD."),
    output: Path = typer.Option(..., "--output", "-o", help="Output CSV path."),
    api_key_env: str = typer.Option("FRED_API_KEY", "--api-key-env", help="FRED API key env var."),
) -> None:
    """Fetch one FRED series and save normalized raw observations as CSV."""

    try:
        saved_path = fetch_fred_series_to_csv(
            series_id=series,
            start=start,
            end=end,
            output=output,
            api_key_env=api_key_env,
        )
    except (FredApiError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"Saved FRED series {series} to {saved_path}")


@app.command("fetch-fred-batch")
def fetch_fred_batch(
    config: Path = typer.Option(
        Path("data_mining/configs/default.yaml"),
        "--config",
        "-c",
        help="Path to the YAML configuration file.",
    ),
    start: str | None = typer.Option(None, "--start", help="Observation start date, YYYY-MM-DD."),
    end: str | None = typer.Option(None, "--end", help="Observation end date, YYYY-MM-DD."),
) -> None:
    """Fetch configured FRED series and save one raw CSV file per series."""

    loaded_config = load_config(config)
    fred_config = loaded_config.sources.get("fred", {})
    if not fred_config.get("enabled", True):
        console.print("FRED source is disabled in config.")
        raise typer.Exit(code=0)

    series_ids = fred_config.get("series", [])
    if not series_ids:
        console.print("No FRED series configured.")
        raise typer.Exit(code=1)

    try:
        saved_paths = fetch_fred_batch_to_csv(
            series_ids=series_ids,
            start=start,
            end=end,
            output_dir=fred_config.get("output_dir", "data/raw/fred"),
            api_key_env=fred_config.get("api_key_env", "FRED_API_KEY"),
        )
    except (FredApiError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    for saved_path in saved_paths:
        console.print(f"Saved {saved_path}")


@app.command("build-fred-report")
def build_fred_report(
    fred_dir: Path = typer.Option(
        Path("data/raw/fred"),
        "--fred-dir",
        help="Directory containing raw FRED CSV files.",
    ),
    output: Path = typer.Option(
        Path("visualization/reports/fred_macro_snapshot.html"),
        "--output",
        "-o",
        help="Output HTML report path.",
    ),
) -> None:
    """Build a static HTML snapshot report from raw FRED CSV files."""

    try:
        saved_path = build_fred_html_report(fred_dir=fred_dir, output=output)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"Saved FRED HTML report to {saved_path}")


@app.command("build-fred-macro-features")
def build_fred_macro_features(
    input_dir: Path = typer.Option(
        Path("data/raw/fred"),
        "--input-dir",
        help="Directory containing local FRED CSV files.",
    ),
    output_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--output-dir",
        help="Directory for macro analysis outputs.",
    ),
) -> None:
    """Build preliminary macro features from local FRED CSV files."""

    try:
        result = run_fred_macro_analysis(input_dir=input_dir, output_dir=output_dir)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    if result.input_dir != input_dir:
        console.print(f"Input directory not found; using fallback {result.input_dir}")
    console.print(f"Loaded series: {len(result.loaded_series)}")
    console.print(f"Missing series: {', '.join(result.missing_series) or 'none'}")
    console.print(f"Wide table: {result.wide_path}")
    console.print(f"Features: {result.features_path}")
    console.print(f"Summary: {result.summary_path}")
    console.print(f"Snapshot: {result.snapshot_path}")


@app.command("build-macro-features")
def build_macro_features_command(
    fred_wide: Path = typer.Option(
        Path("analysis/outputs/fred_macro_wide_daily.csv"),
        "--fred-wide",
        help="FRED macro wide daily CSV path.",
    ),
    usd_liquidity: Path = typer.Option(
        Path("analysis/outputs/usd_liquidity_daily.csv"),
        "--usd-liquidity",
        help="USD liquidity daily CSV path.",
    ),
    stablecoins: Path = typer.Option(
        Path("analysis/outputs/stablecoin_liquidity_daily.csv"),
        "--stablecoins",
        help="Stablecoin liquidity daily CSV path.",
    ),
    btc_market: Path = typer.Option(
        Path("analysis/outputs/btc_market_daily.csv"),
        "--btc-market",
        help="BTC market daily CSV path.",
    ),
    transmission: Path = typer.Option(
        Path("analysis/outputs/transmission_features_daily.csv"),
        "--transmission",
        help="Transmission features daily CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--output",
        "-o",
        help="Output consolidated macro features CSV path.",
    ),
    audit_output: Path = typer.Option(
        Path("analysis/outputs/macro_feature_audit.csv"),
        "--audit-output",
        help="Output macro feature audit CSV path.",
    ),
    latest_output: Path = typer.Option(
        Path("analysis/outputs/macro_feature_latest_snapshot.csv"),
        "--latest-output",
        help="Output latest feature snapshot CSV path.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build the consolidated authoritative macro_features_daily table."""

    try:
        result = consolidate_macro_features(
            fred_wide_path=fred_wide,
            usd_liquidity_path=usd_liquidity,
            stablecoins_path=stablecoins,
            btc_market_path=btc_market,
            transmission_path=transmission,
            output_path=output,
            audit_output_path=audit_output,
            latest_output_path=latest_output,
            snapshot_path=snapshot,
        )
    except (MacroFeatureConsolidationError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    for missing in result.missing_inputs:
        console.print(f"[yellow]Warning: missing input {missing}[/yellow]")
    for warning in result.warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")
    date_min = result.features["date"].min()
    date_max = result.features["date"].max()
    console.print(f"Macro features output: {output}")
    console.print(f"Feature audit output: {audit_output}")
    console.print(f"Latest feature snapshot output: {latest_output}")
    console.print(f"Updated snapshot: {snapshot}")
    console.print(f"Fields: {len(result.features.columns)}")
    console.print(f"Date range: {date_min.date()} to {date_max.date()}")


@app.command("review-feature-eligibility")
def review_feature_eligibility_command(
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Consolidated macro features CSV path.",
    ),
    audit: Path = typer.Option(
        Path("analysis/outputs/macro_feature_audit.csv"),
        "--audit",
        help="Macro feature audit CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/feature_eligibility.csv"),
        "--output",
        "-o",
        help="Output feature eligibility CSV path.",
    ),
    scoring_output: Path = typer.Option(
        Path("analysis/outputs/scoring_feature_candidates.csv"),
        "--scoring-output",
        help="Output scoring feature candidates CSV path.",
    ),
    research_output: Path = typer.Option(
        Path("analysis/outputs/research_feature_candidates.csv"),
        "--research-output",
        help="Output research feature candidates CSV path.",
    ),
    dashboard_output: Path = typer.Option(
        Path("analysis/outputs/dashboard_feature_candidates.csv"),
        "--dashboard-output",
        help="Output dashboard feature candidates CSV path.",
    ),
    excluded_output: Path = typer.Option(
        Path("analysis/outputs/excluded_features.csv"),
        "--excluded-output",
        help="Output excluded features CSV path.",
    ),
    summary_output: Path = typer.Option(
        Path("analysis/outputs/feature_eligibility_latest_summary.json"),
        "--summary-output",
        help="Output feature eligibility summary JSON path.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Review feature eligibility for scoring, research, dashboard, and exclusions."""

    if not audit.exists():
        console.print(f"[yellow]Warning: audit file missing; generating base audit from {features}[/yellow]")
    try:
        result = run_feature_eligibility_review(
            features_path=features,
            audit_path=audit,
            output_path=output,
            scoring_output_path=scoring_output,
            research_output_path=research_output,
            dashboard_output_path=dashboard_output,
            excluded_output_path=excluded_output,
            summary_output_path=summary_output,
            snapshot_path=snapshot,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Feature eligibility output: {output}")
    console.print(f"Scoring candidates output: {scoring_output}")
    console.print(f"Research candidates output: {research_output}")
    console.print(f"Dashboard candidates output: {dashboard_output}")
    console.print(f"Excluded features output: {excluded_output}")
    console.print(f"Summary output: {summary_output}")
    console.print(f"Updated snapshot: {snapshot}")
    console.print(f"Scoring ready: {result.summary['scoring_ready_count']}")
    console.print(f"Research only: {result.summary['research_only_count']}")
    console.print(f"Dashboard only: {result.summary['dashboard_only_count']}")
    console.print(f"Excluded: {result.summary['excluded_count']}")
    for warning in result.warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("build-macro-scores")
def build_macro_scores_command(
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Consolidated macro features CSV path.",
    ),
    candidates: Path = typer.Option(
        Path("analysis/outputs/scoring_feature_candidates.csv"),
        "--candidates",
        help="Scoring feature candidates CSV path from Step 5B.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/macro_scores_daily.csv"),
        "--output",
        "-o",
        help="Output macro scores CSV path.",
    ),
    contributions_output: Path = typer.Option(
        Path("analysis/outputs/macro_score_contributions_daily.csv"),
        "--contributions-output",
        help="Output long-form score contributions CSV path.",
    ),
    audit_output: Path = typer.Option(
        Path("analysis/outputs/macro_score_audit.csv"),
        "--audit-output",
        help="Output macro score audit CSV path.",
    ),
    latest_output: Path = typer.Option(
        Path("analysis/outputs/macro_score_latest_snapshot.csv"),
        "--latest-output",
        help="Output latest macro score snapshot CSV path.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build rule-based macro scores from scoring-ready features."""

    try:
        scores, _, _ = run_macro_scoring(
            features_path=features,
            candidates_path=candidates,
            output_path=output,
            contributions_output_path=contributions_output,
            audit_output_path=audit_output,
            latest_output_path=latest_output,
            snapshot_path=snapshot,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    latest = scores.sort_values("date").iloc[-1]
    console.print(f"Macro scores output: {output}")
    console.print(f"Score contributions output: {contributions_output}")
    console.print(f"Score audit output: {audit_output}")
    console.print(f"Latest score snapshot output: {latest_output}")
    console.print(f"Updated snapshot: {snapshot}")
    console.print(f"Latest macro_liquidity_score: {latest.get('macro_liquidity_score'):.2f}")
    console.print(f"Latest score_coverage_ratio: {latest.get('score_coverage_ratio'):.2f}")


@app.command("update-score-dashboard")
def update_score_dashboard(
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    dashboard_output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--dashboard-output",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Build macro scores and rebuild the static dashboard."""

    try:
        run_macro_scoring(
            features_path=analysis_dir / "macro_features_daily.csv",
            candidates_path=analysis_dir / "scoring_feature_candidates.csv",
            output_path=analysis_dir / "macro_scores_daily.csv",
            contributions_output_path=analysis_dir / "macro_score_contributions_daily.csv",
            audit_output_path=analysis_dir / "macro_score_audit.csv",
            latest_output_path=analysis_dir / "macro_score_latest_snapshot.csv",
            snapshot_path=analysis_dir / "macro_snapshot_latest.json",
        )
        dashboard_warnings = build_dashboard(analysis_dir=analysis_dir, output=dashboard_output)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"Dashboard output: {dashboard_output}")
    for warning in dashboard_warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("build-market-regime")
def build_market_regime_command(
    scores: Path = typer.Option(
        Path("analysis/outputs/macro_scores_daily.csv"),
        "--scores",
        help="Macro scores daily CSV path.",
    ),
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Consolidated macro features CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/market_regime_daily.csv"),
        "--output",
        "-o",
        help="Output market regime daily CSV path.",
    ),
    transitions_output: Path = typer.Option(
        Path("analysis/outputs/market_regime_transitions.csv"),
        "--transitions-output",
        help="Output regime transitions CSV path.",
    ),
    audit_output: Path = typer.Option(
        Path("analysis/outputs/market_regime_audit.csv"),
        "--audit-output",
        help="Output regime audit CSV path.",
    ),
    latest_output: Path = typer.Option(
        Path("analysis/outputs/market_regime_latest_snapshot.csv"),
        "--latest-output",
        help="Output latest regime snapshot CSV path.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build rule-based market regime labels from macro scores."""

    try:
        regime, transitions, _ = run_market_regime_update(
            scores_path=scores,
            features_path=features,
            output_path=output,
            transitions_output_path=transitions_output,
            audit_output_path=audit_output,
            latest_output_path=latest_output,
            snapshot_path=snapshot,
        )
    except (RegimeError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    latest = regime.sort_values("date").iloc[-1]
    console.print(f"Market regime output: {output}")
    console.print(f"Regime transitions output: {transitions_output}")
    console.print(f"Regime audit output: {audit_output}")
    console.print(f"Latest regime snapshot output: {latest_output}")
    console.print(f"Updated snapshot: {snapshot}")
    console.print(f"Latest regime: {latest.get('regime')}")
    console.print(f"Latest regime_score: {latest.get('regime_score'):.2f}")
    console.print(f"Latest regime_confidence: {latest.get('regime_confidence'):.2f}")
    console.print(f"Transitions: {len(transitions)}")


@app.command("update-regime-dashboard")
def update_regime_dashboard(
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    dashboard_output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--dashboard-output",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Build market regime outputs and rebuild the static dashboard."""

    try:
        run_market_regime_update(
            scores_path=analysis_dir / "macro_scores_daily.csv",
            features_path=analysis_dir / "macro_features_daily.csv",
            output_path=analysis_dir / "market_regime_daily.csv",
            transitions_output_path=analysis_dir / "market_regime_transitions.csv",
            audit_output_path=analysis_dir / "market_regime_audit.csv",
            latest_output_path=analysis_dir / "market_regime_latest_snapshot.csv",
            snapshot_path=analysis_dir / "macro_snapshot_latest.json",
        )
        dashboard_warnings = build_dashboard(analysis_dir=analysis_dir, output=dashboard_output)
    except (RegimeError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"Dashboard output: {dashboard_output}")
    for warning in dashboard_warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("build-dashboard")
def build_static_dashboard(
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Directory containing analysis output files.",
    ),
    output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--output",
        "-o",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Build a static macro dashboard from analysis outputs."""

    summary_path = analysis_dir / "fred_series_summary.csv"
    features_path = analysis_dir / "macro_features_daily.csv"
    snapshot_path = analysis_dir / "macro_snapshot_latest.json"
    try:
        warnings = build_dashboard(analysis_dir=analysis_dir, output=output)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Summary input: {summary_path}")
    console.print(f"Features input: {features_path}")
    console.print(f"Snapshot input: {snapshot_path}")
    console.print(f"Dashboard output: {output}")
    for warning in warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("build-compact-dashboard")
def build_compact_dashboard_command(
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Directory containing analysis output files.",
    ),
    output: Path = typer.Option(
        Path("visualization/outputs/dashboard_compact.html"),
        "--output",
        "-o",
        help="Output compact dashboard HTML path.",
    ),
) -> None:
    """Build a compact daily-use dashboard with key state and scores only."""

    inputs = build_compact_dashboard(analysis_dir=analysis_dir, output=output)
    score_values = {}
    score_values.update(inputs.snapshot.get("key_features") or {})
    score_values.update(inputs.snapshot.get("score_summary") or {})
    if inputs.score_latest is not None and not inputs.score_latest.empty:
        score_values.update(inputs.score_latest.iloc[-1].to_dict())
    regime_values = inputs.snapshot.get("regime_summary") or {}
    if inputs.regime_latest is not None and not inputs.regime_latest.empty:
        regime_values.update(inputs.regime_latest.iloc[-1].to_dict())

    console.print("Loaded files:")
    for path in inputs.loaded_files:
        console.print(f"  {path}")
    if inputs.missing_files:
        console.print("Missing files:")
        for path in inputs.missing_files:
            console.print(f"  {path}")
    console.print(f"Compact dashboard output: {output}")
    console.print(f"Current regime: {regime_values.get('regime', 'n/a')}")
    macro_score = score_values.get("macro_liquidity_score")
    console.print(
        f"Current macro_liquidity_score: {float(macro_score):.2f}"
        if macro_score is not None and not pd.isna(macro_score)
        else "Current macro_liquidity_score: n/a"
    )


@app.command("fetch-tga")
def fetch_tga(
    start_date: str = typer.Option("2020-01-01", "--start-date", help="Start date."),
    end_date: str | None = typer.Option(None, "--end-date", help="Optional end date."),
    output: Path = typer.Option(
        Path("data/raw/treasury/tga_operating_cash_balance.csv"),
        "--output",
        "-o",
        help="Output standardized TGA CSV path.",
    ),
) -> None:
    """Fetch Treasury Operating Cash Balance and save standardized TGA daily CSV."""

    try:
        raw_tga = fetch_tga_operating_cash_balance(start_date=start_date, end_date=end_date)
        tga_daily = build_tga_daily(raw_tga)
        saved_path = save_tga_daily(tga_daily, output)
    except TreasuryTgaError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    account_types = ", ".join(sorted(tga_daily["account_type"].dropna().unique()))
    console.print(f"Fetched TGA rows: {len(tga_daily)}")
    console.print(f"Selected account_type: {account_types}")
    console.print(f"Output: {saved_path}")


@app.command("fetch-tga-raw")
def fetch_tga_raw(
    start_date: str = typer.Option("2020-01-01", "--start-date", help="Start date."),
    end_date: str | None = typer.Option(None, "--end-date", help="Optional end date."),
    output: Path = typer.Option(
        Path("data/raw/treasury/dts_operating_cash_balance_raw.csv"),
        "--output",
        "-o",
        help="Output complete raw Treasury Operating Cash Balance CSV path.",
    ),
) -> None:
    """Fetch complete Treasury Operating Cash Balance raw data without account_type filtering."""

    try:
        raw_tga = fetch_tga_operating_cash_balance(start_date=start_date, end_date=end_date)
        saved_path = save_tga_raw(raw_tga, output)
    except TreasuryTgaError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Fetched raw rows: {len(raw_tga)}")
    console.print(f"Raw output: {saved_path}")


@app.command("inspect-tga-account-types")
def inspect_tga_account_types_command(
    input: Path = typer.Option(
        Path("data/raw/treasury/dts_operating_cash_balance_raw.csv"),
        "--input",
        "-i",
        help="Complete raw Treasury Operating Cash Balance CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/tga_account_type_summary.csv"),
        "--output",
        "-o",
        help="Output account_type summary CSV path.",
    ),
) -> None:
    """Inspect FiscalData account_type coverage for Operating Cash Balance."""

    try:
        raw_tga = pd.read_csv(input)
        summary = inspect_tga_account_types(raw_tga)
        saved_path = save_tga_account_type_summary(summary, output)
    except (TreasuryTgaError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Account type summary: {saved_path}")
    _print_account_type_overview(summary)


@app.command("build-tga-daily")
def build_tga_daily_command(
    input: Path = typer.Option(
        Path("data/raw/treasury/dts_operating_cash_balance_raw.csv"),
        "--input",
        "-i",
        help="Complete raw Treasury Operating Cash Balance CSV path.",
    ),
    output: Path = typer.Option(
        Path("data/processed/treasury/tga_daily.csv"),
        "--output",
        "-o",
        help="Output standardized TGA daily CSV path.",
    ),
    summary_output: Path = typer.Option(
        Path("analysis/outputs/tga_account_type_summary.csv"),
        "--summary-output",
        help="Output account_type summary CSV path.",
    ),
) -> None:
    """Build daily TGA from raw Operating Cash Balance records."""

    try:
        raw_tga = pd.read_csv(input)
        summary = inspect_tga_account_types(raw_tga)
        save_tga_account_type_summary(summary, summary_output)
        tga_daily = build_tga_daily(raw_tga)
        distribution = validate_tga_daily(raw_tga, tga_daily)
        saved_path = save_tga_daily(tga_daily, output)
    except (TreasuryTgaError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Account type summary: {summary_output}")
    _print_account_type_overview(summary)
    console.print(f"TGA daily output: {saved_path}")
    console.print("Selected account_type distribution:")
    _print_account_type_overview(distribution)


@app.command("build-usd-liquidity")
def build_usd_liquidity_command(
    fred_wide: Path = typer.Option(
        Path("analysis/outputs/fred_macro_wide_daily.csv"),
        "--fred-wide",
        help="FRED macro wide daily CSV path.",
    ),
    tga: Path = typer.Option(
        Path("data/processed/treasury/tga_daily.csv"),
        "--tga",
        help="Standardized TGA CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/usd_liquidity_daily.csv"),
        "--output",
        "-o",
        help="Output USD liquidity CSV path.",
    ),
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Macro features CSV path to update.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build TGA-adjusted net liquidity and update macro features/snapshot."""

    try:
        warnings = run_usd_liquidity_update(
            fred_wide_path=fred_wide,
            tga_path=tga,
            output_path=output,
            features_path=features,
            snapshot_path=snapshot,
        )
    except (UsdLiquidityError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"FRED wide input: {fred_wide}")
    console.print(f"TGA input: {tga}")
    console.print(f"USD liquidity output: {output}")
    console.print(f"Updated features: {features}")
    console.print(f"Updated snapshot: {snapshot}")
    for warning in warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("update-tga-liquidity")
def update_tga_liquidity(
    start_date: str = typer.Option("2020-01-01", "--start-date", help="Start date."),
    end_date: str | None = typer.Option(None, "--end-date", help="Optional end date."),
    fred_wide: Path = typer.Option(
        Path("analysis/outputs/fred_macro_wide_daily.csv"),
        "--fred-wide",
        help="FRED macro wide daily CSV path.",
    ),
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    raw_output: Path = typer.Option(
        Path("data/raw/treasury/dts_operating_cash_balance_raw.csv"),
        "--raw-output",
        help="Output complete raw Treasury Operating Cash Balance CSV path.",
    ),
    tga_output: Path = typer.Option(
        Path("data/processed/treasury/tga_daily.csv"),
        "--tga-output",
        help="Output standardized TGA daily CSV path.",
    ),
) -> None:
    """Fetch TGA, build net liquidity, and update analysis outputs."""

    try:
        raw_tga = fetch_tga_operating_cash_balance(start_date=start_date, end_date=end_date)
        save_tga_raw(raw_tga, raw_output)
        summary = inspect_tga_account_types(raw_tga)
        summary_output = analysis_dir / "tga_account_type_summary.csv"
        save_tga_account_type_summary(summary, summary_output)
        tga_daily = build_tga_daily(raw_tga)
        distribution = validate_tga_daily(raw_tga, tga_daily)
        save_tga_daily(tga_daily, tga_output)
        warnings = run_usd_liquidity_update(
            fred_wide_path=fred_wide,
            tga_path=tga_output,
            output_path=analysis_dir / "usd_liquidity_daily.csv",
            features_path=analysis_dir / "macro_features_daily.csv",
            snapshot_path=analysis_dir / "macro_snapshot_latest.json",
        )
    except (TreasuryTgaError, UsdLiquidityError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Raw TGA output: {raw_output}")
    console.print(f"Account type summary: {analysis_dir / 'tga_account_type_summary.csv'}")
    _print_account_type_overview(summary)
    console.print(f"TGA daily output: {tga_output}")
    console.print("Selected account_type distribution:")
    _print_account_type_overview(distribution)
    console.print(f"USD liquidity output: {analysis_dir / 'usd_liquidity_daily.csv'}")
    console.print(f"Updated features: {analysis_dir / 'macro_features_daily.csv'}")
    console.print(f"Updated snapshot: {analysis_dir / 'macro_snapshot_latest.json'}")
    for warning in warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("update-liquidity-dashboard")
def update_liquidity_dashboard(
    fred_wide: Path = typer.Option(
        Path("analysis/outputs/fred_macro_wide_daily.csv"),
        "--fred-wide",
        help="FRED macro wide daily CSV path.",
    ),
    tga: Path = typer.Option(
        Path("data/processed/treasury/tga_daily.csv"),
        "--tga",
        help="Standardized TGA daily CSV path.",
    ),
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    dashboard_output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--dashboard-output",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Update USD liquidity analysis outputs and rebuild the static dashboard."""

    usd_liquidity_path = analysis_dir / "usd_liquidity_daily.csv"
    features_path = analysis_dir / "macro_features_daily.csv"
    snapshot_path = analysis_dir / "macro_snapshot_latest.json"
    try:
        warnings = run_usd_liquidity_update(
            fred_wide_path=fred_wide,
            tga_path=tga,
            output_path=usd_liquidity_path,
            features_path=features_path,
            snapshot_path=snapshot_path,
        )
        dashboard_warnings = build_dashboard(analysis_dir=analysis_dir, output=dashboard_output)
    except (UsdLiquidityError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"FRED wide input: {fred_wide}")
    console.print(f"TGA input: {tga}")
    console.print(f"USD liquidity output: {usd_liquidity_path}")
    console.print(f"Updated features: {features_path}")
    console.print(f"Updated snapshot: {snapshot_path}")
    console.print(f"Dashboard output: {dashboard_output}")
    for warning in warnings + dashboard_warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("fetch-stablecoins")
def fetch_stablecoins(
    output_current: Path = typer.Option(
        Path("data/raw/defillama/stablecoins_current.json"),
        "--output-current",
        help="Output DeFiLlama current stablecoins raw JSON path.",
    ),
    output_charts: Path = typer.Option(
        Path("data/raw/defillama/stablecoincharts_all.json"),
        "--output-charts",
        help="Output DeFiLlama total stablecoin charts raw JSON path.",
    ),
) -> None:
    """Fetch raw DeFiLlama stablecoin current and chart payloads."""

    try:
        current = fetch_stablecoins_current()
        charts = fetch_stablecoin_charts_all()
        save_json(current, output_current)
        if charts is not None:
            save_json(charts, output_charts)
    except (DeFiLlamaStablecoinError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Current stablecoins raw output: {output_current}")
    if charts is None:
        console.print(f"[yellow]Warning: charts endpoint failed; not updated: {output_charts}[/yellow]")
    else:
        console.print(f"Stablecoin charts raw output: {output_charts}")


@app.command("build-stablecoin-liquidity")
def build_stablecoin_liquidity_command(
    current: Path = typer.Option(
        Path("data/raw/defillama/stablecoins_current.json"),
        "--current",
        help="DeFiLlama current stablecoins raw JSON path.",
    ),
    charts: Path = typer.Option(
        Path("data/raw/defillama/stablecoincharts_all.json"),
        "--charts",
        help="DeFiLlama total stablecoin charts raw JSON path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/stablecoin_liquidity_daily.csv"),
        "--output",
        "-o",
        help="Output stablecoin liquidity CSV path.",
    ),
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Macro features CSV path to update.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build stablecoin liquidity features and update macro outputs."""

    summary_path = output.parent / "stablecoin_current_summary.csv"
    try:
        current_df = parse_stablecoins_current(load_json(current))
        current_summary = build_stablecoin_current_summary(current_df)
        charts_df = parse_stablecoin_charts_all(load_json(charts))
        warnings = run_stablecoin_liquidity_update(
            charts_df=charts_df,
            current_summary=current_summary,
            output_path=output,
            features_path=features,
            snapshot_path=snapshot,
            current_summary_path=summary_path,
        )
    except (DeFiLlamaStablecoinError, StablecoinLiquidityError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Current input: {current}")
    console.print(f"Charts input: {charts}")
    console.print(f"Stablecoin liquidity output: {output}")
    console.print(f"Current summary output: {summary_path}")
    console.print(f"Updated features: {features}")
    console.print(f"Updated snapshot: {snapshot}")
    for warning in warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("update-stablecoin-dashboard")
def update_stablecoin_dashboard(
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    raw_dir: Path = typer.Option(
        Path("data/raw/defillama"),
        "--raw-dir",
        help="DeFiLlama raw output directory.",
    ),
    dashboard_output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--dashboard-output",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Fetch stablecoins, update stablecoin analysis, and rebuild dashboard."""

    output_current = raw_dir / "stablecoins_current.json"
    output_charts = raw_dir / "stablecoincharts_all.json"
    stablecoin_output = analysis_dir / "stablecoin_liquidity_daily.csv"
    summary_path = analysis_dir / "stablecoin_current_summary.csv"
    features_path = analysis_dir / "macro_features_daily.csv"
    snapshot_path = analysis_dir / "macro_snapshot_latest.json"
    try:
        current = fetch_stablecoins_current()
        charts = fetch_stablecoin_charts_all()
        save_json(current, output_current)
        if charts is None:
            raise StablecoinLiquidityError("stablecoincharts/all response is unavailable.")
        save_json(charts, output_charts)
        current_df = parse_stablecoins_current(current)
        current_summary = build_stablecoin_current_summary(current_df)
        charts_df = parse_stablecoin_charts_all(charts)
        warnings = run_stablecoin_liquidity_update(
            charts_df=charts_df,
            current_summary=current_summary,
            output_path=stablecoin_output,
            features_path=features_path,
            snapshot_path=snapshot_path,
            current_summary_path=summary_path,
        )
        dashboard_warnings = build_dashboard(analysis_dir=analysis_dir, output=dashboard_output)
    except (
        DeFiLlamaStablecoinError,
        StablecoinLiquidityError,
        FileNotFoundError,
        OSError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"Current stablecoins raw output: {output_current}")
    console.print(f"Stablecoin charts raw output: {output_charts}")
    console.print(f"Stablecoin liquidity output: {stablecoin_output}")
    console.print(f"Current summary output: {summary_path}")
    console.print(f"Updated features: {features_path}")
    console.print(f"Updated snapshot: {snapshot_path}")
    console.print(f"Dashboard output: {dashboard_output}")
    for warning in warnings + dashboard_warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


@app.command("fetch-btc-market")
def fetch_btc_market(
    start_date: str = typer.Option("2020-01-01", "--start-date", help="Start date."),
    end_date: str | None = typer.Option(None, "--end-date", help="Optional end date."),
    output: Path = typer.Option(
        Path("data/raw/coingecko/btc_market_chart.json"),
        "--output",
        "-o",
        help="Output CoinGecko BTC market chart raw JSON path.",
    ),
) -> None:
    """Fetch raw BTC market chart data from CoinGecko."""

    try:
        raw = fetch_btc_market_chart(start_date=start_date, end_date=end_date)
        save_btc_json(raw, output)
    except (CoinGeckoBtcError, OSError) as exc:
        if not output.exists():
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None
        console.print(f"[yellow]Warning: {exc}; using cached raw JSON at {output}[/yellow]")
    console.print(f"BTC market raw output: {output}")


@app.command("build-transmission-features")
def build_transmission_features_command(
    macro_features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--macro-features",
        help="Macro features CSV path.",
    ),
    btc_raw: Path = typer.Option(
        Path("data/raw/coingecko/btc_market_chart.json"),
        "--btc-raw",
        help="CoinGecko BTC market chart raw JSON path.",
    ),
    btc_output: Path = typer.Option(
        Path("analysis/outputs/btc_market_daily.csv"),
        "--btc-output",
        help="Output parsed BTC market daily CSV path.",
    ),
    output: Path = typer.Option(
        Path("analysis/outputs/transmission_features_daily.csv"),
        "--output",
        "-o",
        help="Output transmission features CSV path.",
    ),
    features: Path = typer.Option(
        Path("analysis/outputs/macro_features_daily.csv"),
        "--features",
        help="Macro features CSV path to update.",
    ),
    snapshot: Path = typer.Option(
        Path("analysis/outputs/macro_snapshot_latest.json"),
        "--snapshot",
        help="Macro snapshot JSON path to update.",
    ),
) -> None:
    """Build BTC/stablecoin transmission features and update macro outputs."""

    try:
        btc_market = parse_btc_market_chart(load_btc_json(btc_raw))
        save_btc_market_daily(btc_market, btc_output)
        run_transmission_update(
            macro_features_path=macro_features,
            btc_market=btc_market,
            btc_output_path=btc_output,
            output_path=output,
            features_path=features,
            snapshot_path=snapshot,
        )
    except (CoinGeckoBtcError, TransmissionFeatureError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"Macro features input: {macro_features}")
    console.print(f"BTC raw input: {btc_raw}")
    console.print(f"BTC market output: {btc_output}")
    console.print(f"Transmission output: {output}")
    console.print(f"Updated features: {features}")
    console.print(f"Updated snapshot: {snapshot}")


@app.command("update-transmission-dashboard")
def update_transmission_dashboard(
    start_date: str = typer.Option("2020-01-01", "--start-date", help="Start date."),
    end_date: str | None = typer.Option(None, "--end-date", help="Optional end date."),
    analysis_dir: Path = typer.Option(
        Path("analysis/outputs"),
        "--analysis-dir",
        help="Analysis output directory.",
    ),
    raw_output: Path = typer.Option(
        Path("data/raw/coingecko/btc_market_chart.json"),
        "--raw-output",
        help="Output CoinGecko BTC market chart raw JSON path.",
    ),
    dashboard_output: Path = typer.Option(
        Path("visualization/outputs/dashboard.html"),
        "--dashboard-output",
        help="Output dashboard HTML path.",
    ),
) -> None:
    """Fetch BTC data, update transmission features, and rebuild dashboard."""

    btc_output = analysis_dir / "btc_market_daily.csv"
    transmission_output = analysis_dir / "transmission_features_daily.csv"
    features_path = analysis_dir / "macro_features_daily.csv"
    snapshot_path = analysis_dir / "macro_snapshot_latest.json"
    try:
        try:
            raw = fetch_btc_market_chart(start_date=start_date, end_date=end_date)
            save_btc_json(raw, raw_output)
        except (CoinGeckoBtcError, OSError) as exc:
            if not raw_output.exists():
                raise
            console.print(
                f"[yellow]Warning: {exc}; using cached raw JSON at {raw_output}[/yellow]"
            )
            raw = load_btc_json(raw_output)
        btc_market = parse_btc_market_chart(raw)
        run_transmission_update(
            macro_features_path=features_path,
            btc_market=btc_market,
            btc_output_path=btc_output,
            output_path=transmission_output,
            features_path=features_path,
            snapshot_path=snapshot_path,
        )
        dashboard_warnings = build_dashboard(analysis_dir=analysis_dir, output=dashboard_output)
    except (CoinGeckoBtcError, TransmissionFeatureError, FileNotFoundError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"BTC market raw output: {raw_output}")
    console.print(f"BTC market output: {btc_output}")
    console.print(f"Transmission output: {transmission_output}")
    console.print(f"Updated features: {features_path}")
    console.print(f"Updated snapshot: {snapshot_path}")
    console.print(f"Dashboard output: {dashboard_output}")
    for warning in dashboard_warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")


def _print_account_type_overview(summary: pd.DataFrame) -> None:
    if summary.empty:
        console.print("No account_type rows found.")
        return
    for row in summary.to_dict("records"):
        latest = row.get("latest_value_billion")
        latest_text = (
            "" if latest is None or pd.isna(latest) else f", latest_billion={latest:.3f}"
        )
        console.print(
            f"- {row.get('account_type')}: {row.get('first_date')} to "
            f"{row.get('last_date')} ({row.get('count')} rows{latest_text})"
        )
