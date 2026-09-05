"""
Gold Analytics & Lakehouse Pipeline for SportsPulse.
Builds Star Schema dimensional tables, calculates HRV and TRIMP physiological metrics, and initializes DuckDB.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import time
import yaml
import polars as pl
from rich.console import Console
from rich.table import Table

from sportspulse.analytics.star_schema import build_star_schema
from sportspulse.database.lakehouse import LakehouseDB

console = Console()


def load_yaml(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_gold_pipeline(
    silver_dir: Optional[str] = None,
    gold_dir: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the Gold Layer analytics pipeline:
    1. Reads Silver Parquet tables
    2. Builds Star Schema (Dimensions & Facts)
    3. Computes HRV and TRIMP markers
    4. Writes Gold Parquet files
    5. Stores tables and analytical views in DuckDB
    """
    settings = load_yaml("config/settings.yaml")
    sports_cfg = load_yaml("config/sports_mapping.yaml")["sports"]

    s_dir = Path(silver_dir or settings["paths"]["silver_dir"])
    g_dir = Path(gold_dir or settings["paths"]["gold_dir"])
    g_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_path or settings["paths"]["database_file"]

    console.print(f"[bold cyan]🥇 Starting Gold Analytics & Lakehouse Pipeline[/bold cyan]")
    console.print(f"📥 Reading Silver from: [yellow]{s_dir}[/yellow]")
    console.print(f"💾 Gold Parquet Storage: [yellow]{g_dir}[/yellow]")
    console.print(f"🦆 DuckDB Database: [yellow]{db_file}[/yellow]\n")

    start_time = time.time()

    # 1. Load Silver tables
    df_telemetry = pl.read_parquet(s_dir / "silver_telemetry_enriched.parquet")
    df_athletes = pl.read_parquet(s_dir / "silver_athletes.parquet")

    # 2. Build Star Schema
    console.print("[cyan]⭐ Modeling Star Schema and calculating HRV & TRIMP metrics...[/cyan]")
    gold_tables = build_star_schema(df_telemetry, df_athletes, sports_cfg)

    # 3. Write Gold Parquet files
    console.print("\n[cyan]💾 Saving Gold Parquet tables...[/cyan]")
    for table_name, df_table in gold_tables.items():
        out_file = g_dir / f"{table_name}.parquet"
        df_table.write_parquet(out_file, compression="zstd" if "telemetry" in table_name else "snappy")
        console.print(f"  ✓ Saved [green]{table_name}[/green] ({len(df_table):,} rows) -> [yellow]{out_file}[/yellow]")

    # 4. Initialize DuckDB Database
    console.print(f"\n[cyan]🦆 Initializing DuckDB Lakehouse at {db_file}...[/cyan]")
    lakehouse = LakehouseDB(db_path=db_file)
    lakehouse.init_gold_tables(gold_tables)

    # 5. Display Summary Table
    summary_df = lakehouse.query("SELECT * FROM vw_sport_intensity_comparison")
    lakehouse.close()

    table = Table(title="🏆 Sports Intensity & Cardiorespiratory Summary (Gold Layer)")
    table.add_column("Sport", style="bold cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Sessions", justify="right", style="green")
    table.add_column("Avg Duration", justify="right")
    table.add_column("Avg HR (bpm)", justify="right")
    table.add_column("Peak HR (bpm)", justify="right", style="red")
    table.add_column("TRIMP (Banister)", justify="right", style="bold yellow")
    table.add_column("HRV RMSSD (ms)", justify="right", style="cyan")

    for row in summary_df.iter_rows(named=True):
        table.add_row(
            f"{row['sport_name']} ({row['sport_code']})",
            row["sport_category"],
            str(row["total_sessions"]),
            f"{row['avg_duration_min']} min",
            f"{row['avg_hr_bpm']}",
            f"{row['peak_hr_bpm']}",
            f"{row['avg_banister_trimp']}",
            f"{row['avg_rmssd_ms'] if row['avg_rmssd_ms'] is not None else 'N/A'}",
        )

    console.print("\n")
    console.print(table)

    elapsed = round(time.time() - start_time, 2)
    console.print(f"\n[bold green]✨ Gold Analytics successfully completed in {elapsed}s![/bold green]\n")

    return {
        "gold_tables_count": len(gold_tables),
        "total_sessions": len(gold_tables["fact_training_session"]),
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    run_gold_pipeline()
