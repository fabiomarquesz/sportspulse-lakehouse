"""
Bronze Ingestion Pipeline for SportsPulse Lakehouse.
Extracts raw data from SportDB (.mat, Dem.txt, TrNote.txt) and saves to Bronze Parquet tables.
"""

import time
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from sportspulse.ingestion.mat_parser import parse_mat_file
from sportspulse.ingestion.metadata_parser import parse_dem_file, parse_trnote_file

console = Console()


def load_settings(config_path: str = "config/settings.yaml") -> dict[str, Any]:
    """Loads configuration settings from YAML."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_bronze_ingestion(
    source_dir: str | None = None,
    output_bronze_dir: str | None = None,
    include_ecg_250hz: bool = True,
) -> dict[str, Any]:
    """
    Scans the SportDB dataset and executes the Bronze Layer Ingestion.
    """
    settings = load_settings()
    raw_path = Path(source_dir or settings["paths"]["raw_source_dir"])
    bronze_path = Path(output_bronze_dir or settings["paths"]["bronze_dir"])

    bronze_path.mkdir(parents=True, exist_ok=True)
    telemetry_1hz_dir = bronze_path / "telemetry_1hz"
    ecg_250hz_dir = bronze_path / "ecg_250hz"
    telemetry_1hz_dir.mkdir(parents=True, exist_ok=True)
    if include_ecg_250hz:
        ecg_250hz_dir.mkdir(parents=True, exist_ok=True)

    console.print("[bold cyan]🚀 Starting Bronze Ingestion Pipeline[/bold cyan]")
    console.print(f"📁 Source: [yellow]{raw_path}[/yellow]")
    console.print(f"💾 Bronze Destination: [yellow]{bronze_path}[/yellow]")

    # Find all sessions
    session_paths = sorted(list(raw_path.glob("*/*/*/Data.mat")))
    total_sessions = len(session_paths)
    console.print(f"🔍 Found [bold green]{total_sessions}[/bold green] sessions to ingest.\n")

    all_demographics: list[pl.DataFrame] = []
    all_phases: list[pl.DataFrame] = []
    all_telemetry_1hz: list[pl.DataFrame] = []
    manifest_records: list[dict[str, Any]] = []

    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Ingesting sessions...", total=total_sessions)

        for mat_file in session_paths:
            crd_dir = mat_file.parent
            subject_dir = crd_dir.parent
            sport_dir = subject_dir.parent

            sport_code = sport_dir.name
            subject_id = subject_dir.name
            session_id = crd_dir.name

            progress.update(task, description=f"[cyan]Ingesting {sport_code}/{subject_id}/{session_id}...")

            dem_file = crd_dir / "Dem.txt"
            trnote_file = crd_dir / "TrNote.txt"

            status = "SUCCESS"
            error_msg = None
            duration_sec = 0
            n_ecg_samples = 0

            try:
                # 1. Parse Biosignals
                bio_data = parse_mat_file(mat_file, sport_code, subject_id, session_id)
                df_1hz = bio_data.to_1hz_dataframe()
                all_telemetry_1hz.append(df_1hz)
                duration_sec = bio_data.duration_seconds
                n_ecg_samples = len(bio_data.ecg)

                # Save 250Hz ECG per session if enabled
                if include_ecg_250hz:
                    session_ecg_dir = ecg_250hz_dir / f"sport={sport_code}"
                    session_ecg_dir.mkdir(parents=True, exist_ok=True)
                    df_ecg = bio_data.to_ecg_dataframe()
                    ecg_out_file = session_ecg_dir / f"{subject_id}_{session_id}_ecg.parquet"
                    df_ecg.write_parquet(ecg_out_file, compression="zstd")

                # 2. Parse Demographics
                if dem_file.exists():
                    df_dem = parse_dem_file(dem_file, sport_code, subject_id, session_id)
                    all_demographics.append(df_dem)

                # 3. Parse Training Notes / Phases
                if trnote_file.exists():
                    df_tr = parse_trnote_file(trnote_file, sport_code, subject_id, session_id)
                    all_phases.append(df_tr)

            except Exception as e:
                status = "FAILED"
                error_msg = str(e)
                console.print(f"[red]Error in {sport_code}/{subject_id}/{session_id}: {e}[/red]")

            manifest_records.append(
                {
                    "sport_code": sport_code,
                    "subject_id": subject_id,
                    "session_id": session_id,
                    "duration_seconds": duration_sec,
                    "ecg_samples_count": n_ecg_samples,
                    "ingestion_status": status,
                    "error_message": error_msg,
                    "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            progress.advance(task)

    # Consolidate and write Bronze tables
    console.print("\n[cyan]Writing consolidated Bronze Parquet tables...[/cyan]")

    if all_demographics:
        bronze_dem_df = pl.concat(all_demographics)
        dem_path = bronze_path / "bronze_demographics.parquet"
        bronze_dem_df.write_parquet(dem_path, compression="snappy")
        console.print(f"  ✓ [green]Demographics[/green]: {len(bronze_dem_df)} records -> [yellow]{dem_path}[/yellow]")

    if all_phases:
        bronze_phases_df = pl.concat(all_phases)
        phases_path = bronze_path / "bronze_training_phases.parquet"
        bronze_phases_df.write_parquet(phases_path, compression="snappy")
        console.print(
            f"  ✓ [green]Training Phases[/green]: {len(bronze_phases_df)} records -> [yellow]{phases_path}[/yellow]"
        )

    if all_telemetry_1hz:
        bronze_1hz_df = pl.concat(all_telemetry_1hz)
        # Partition 1Hz telemetry by sport_code for fast querying
        telemetry_path = bronze_path / "bronze_telemetry_1hz.parquet"
        bronze_1hz_df.write_parquet(telemetry_path, compression="zstd")
        console.print(
            f"  ✓ [green]Telemetry 1Hz[/green]: {len(bronze_1hz_df):,} seconds of biosignals -> [yellow]{telemetry_path}[/yellow]"
        )

    manifest_df = pl.DataFrame(manifest_records)
    manifest_path = bronze_path / "bronze_ingestion_manifest.parquet"
    manifest_df.write_parquet(manifest_path, compression="snappy")
    console.print(
        f"  ✓ [green]Manifest & Audit[/green]: {len(manifest_df)} sessions -> [yellow]{manifest_path}[/yellow]"
    )

    elapsed = round(time.time() - start_time, 2)
    console.print(f"\n[bold green]✨ Bronze Ingestion successfully completed in {elapsed}s![/bold green]\n")

    return {
        "total_sessions": total_sessions,
        "successful_sessions": len([r for r in manifest_records if r["ingestion_status"] == "SUCCESS"]),
        "telemetry_rows": len(bronze_1hz_df) if all_telemetry_1hz else 0,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    run_bronze_ingestion()
