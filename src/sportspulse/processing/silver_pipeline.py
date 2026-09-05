"""
Silver Processing Pipeline for SportsPulse Lakehouse.
Cleans raw biosignals, aligns training phases, and enriches data with athlete demographics and sports metadata.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import time
import yaml
import polars as pl
from rich.console import Console

from sportspulse.processing.signal_cleaner import SignalCleaner
from sportspulse.processing.phase_aligner import align_telemetry_with_phases

console = Console()


def load_yaml(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_silver_pipeline(
    bronze_dir: Optional[str] = None,
    silver_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the Silver Layer processing:
    1. Reads Bronze Parquet tables
    2. Cleans raw biosignals and handles artifacts
    3. Aligns telemetry with training phases
    4. Enriches with athlete demographics and sport categories
    5. Computes derived physiological metrics (%HRR, HR/BR ratio)
    """
    settings = load_yaml("config/settings.yaml")
    sports_cfg = load_yaml("config/sports_mapping.yaml")["sports"]

    b_dir = Path(bronze_dir or settings["paths"]["bronze_dir"])
    s_dir = Path(silver_dir or settings["paths"]["silver_dir"])
    s_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold cyan]🥈 Starting Silver Processing Pipeline[/bold cyan]")
    console.print(f"📥 Reading Bronze from: [yellow]{b_dir}[/yellow]")
    console.print(f"💾 Silver Destination: [yellow]{s_dir}[/yellow]\n")

    start_time = time.time()

    # 1. Load Bronze Tables
    df_telemetry = pl.read_parquet(b_dir / "bronze_telemetry_1hz.parquet")
    df_demographics = pl.read_parquet(b_dir / "bronze_demographics.parquet")
    df_phases = pl.read_parquet(b_dir / "bronze_training_phases.parquet")

    console.print(f"  • Loaded Bronze Telemetry: [green]{len(df_telemetry):,}[/green] rows")
    console.print(f"  • Loaded Demographics: [green]{len(df_demographics)}[/green] athletes")
    console.print(f"  • Loaded Training Phases: [green]{len(df_phases)}[/green] records")

    # 2. Clean Signals
    console.print("\n[cyan]⚙️  Cleaning biosignals (HR, BR, RR) and smoothing trends...[/cyan]")
    cleaner = SignalCleaner(
        hr_min=settings["signal_thresholds"]["hr_min_bpm"],
        hr_max=settings["signal_thresholds"]["hr_max_bpm"],
        br_min=settings["signal_thresholds"]["br_min_rpm"],
        br_max=settings["signal_thresholds"]["br_max_rpm"],
        rr_min=settings["signal_thresholds"]["rr_min_ms"],
        rr_max=settings["signal_thresholds"]["rr_max_ms"],
    )
    df_cleaned = cleaner.clean_telemetry(df_telemetry)

    # 3. Align with Training Phases
    console.print("[cyan]⏱️  Aligning 1Hz telemetry with training protocol phases...[/cyan]")
    df_aligned = align_telemetry_with_phases(df_cleaned, df_phases)

    # 4. Enrich with Sports Metadata
    console.print("[cyan]🏷️  Enriching with Sports taxonomy and categories...[/cyan]")
    sports_list = []
    for code, info in sports_cfg.items():
        sports_list.append({
            "sport_code": code,
            "sport_name": info["name"],
            "sport_category": info["category"],
            "sport_description": info["description"],
        })
    df_sports_meta = pl.DataFrame(sports_list)

    # 5. Join Demographics and Sports Metadata
    df_enriched = (
        df_aligned
        .join(df_demographics, on=["sport_code", "subject_id", "session_id"], how="left")
        .join(df_sports_meta, on="sport_code", how="left")
    )

    # 6. Compute Derived Physiological Metrics
    console.print("[cyan]🧮 Calculating physiological derived metrics (%HRR, HR/BR coupling)...[/cyan]")
    # Max HR estimation: Tanaka formula (208 - 0.7 * age) or default 190
    df_enriched = df_enriched.with_columns([
        pl.when(pl.col("age_years").is_not_null())
        .then(208.0 - 0.7 * pl.col("age_years"))
        .otherwise(190.0)
        .alias("hr_max_est"),
        
        # Instantaneous HR from RR interval
        pl.when(pl.col("rr_ms_clean") > 0)
        .then(60000.0 / pl.col("rr_ms_clean"))
        .otherwise(None)
        .alias("hr_from_rr_bpm"),
    ])

    # Calculate baseline resting HR per session from Rest phase or minimum 5th percentile
    session_hr_rest = (
        df_enriched
        .filter(pl.col("phase_category") == "Rest")
        .group_by(["sport_code", "subject_id", "session_id"])
        .agg(pl.col("hr_bpm_clean").quantile(0.1).alias("hr_rest_est"))
    )

    df_enriched = df_enriched.join(
        session_hr_rest, on=["sport_code", "subject_id", "session_id"], how="left"
    ).with_columns([
        # Fallback for hr_rest_est if no rest phase was present
        pl.coalesce([pl.col("hr_rest_est"), pl.lit(60.0)]).alias("hr_rest_est")
    ]).with_columns([
        # % Heart Rate Reserve (Karvonen method intensity): (%HRR = (HR - HR_rest) / (HR_max - HR_rest) * 100)
        (
            ((pl.col("hr_bpm_clean") - pl.col("hr_rest_est")) / 
             (pl.col("hr_max_est") - pl.col("hr_rest_est")).clip(lower_bound=10.0)) * 100.0
        ).clip(lower_bound=0.0, upper_bound=100.0).alias("hr_reserve_pct"),

        # Cardiorespiratory Coupling Ratio: HR / BR
        pl.when(pl.col("br_rpm_clean") > 0)
        .then(pl.col("hr_bpm_clean") / pl.col("br_rpm_clean"))
        .otherwise(None)
        .alias("hr_br_coupling_ratio"),
    ])

    # 7. Write Silver Tables
    console.print("\n[cyan]💾 Writing Silver Parquet tables...[/cyan]")
    silver_telemetry_file = s_dir / "silver_telemetry_enriched.parquet"
    df_enriched.write_parquet(silver_telemetry_file, compression="zstd")
    console.print(f"  ✓ [green]Enriched Telemetry (Silver)[/green]: {len(df_enriched):,} rows -> [yellow]{silver_telemetry_file}[/yellow]")

    # Unique Athletes Table
    silver_athletes_file = s_dir / "silver_athletes.parquet"
    df_athletes = df_demographics.unique(subset=["sport_code", "subject_id"]).sort(["sport_code", "subject_id"])
    df_athletes.write_parquet(silver_athletes_file, compression="snappy")
    console.print(f"  ✓ [green]Athletes Master (Silver)[/green]: {len(df_athletes)} athletes -> [yellow]{silver_athletes_file}[/yellow]")

    elapsed = round(time.time() - start_time, 2)
    console.print(f"\n[bold green]✨ Silver Processing successfully completed in {elapsed}s![/bold green]\n")

    return {
        "silver_rows": len(df_enriched),
        "athletes_count": len(df_athletes),
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    run_silver_pipeline()
