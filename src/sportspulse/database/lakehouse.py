"""
DuckDB Lakehouse Storage Engine and Analytical Views.
Manages Gold table storage, SQL queries, and zero-copy Parquet interoperability.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import duckdb
import polars as pl
from rich.console import Console

console = Console()


class LakehouseDB:
    def __init__(self, db_path: str = "data/04_gold/sportspulse.duckdb"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))

    def init_gold_tables(self, gold_tables: Dict[str, pl.DataFrame]) -> None:
        """
        Creates physical tables and views in DuckDB from Gold DataFrames.
        """
        for table_name, df in gold_tables.items():
            arrow_table = df.to_arrow()
            self.conn.register("temp_arrow", arrow_table)
            self.conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM temp_arrow")
            self.conn.unregister("temp_arrow")
            console.print(f"  ✓ DuckDB Table: [green]{table_name}[/green] ({len(df):,} records)")

        self._create_analytical_views()

    def _create_analytical_views(self) -> None:
        """Creates pre-aggregated SQL views for high-performance analytical queries."""
        # 1. Cross-sport intensity comparison
        self.conn.execute("""
            CREATE OR REPLACE VIEW vw_sport_intensity_comparison AS
            SELECT 
                s.sport_code,
                s.sport_name,
                s.sport_category,
                COUNT(f.session_key) AS total_sessions,
                COUNT(DISTINCT f.athlete_key) AS total_athletes,
                ROUND(AVG(f.duration_minutes), 1) AS avg_duration_min,
                ROUND(AVG(f.hr_avg_bpm), 1) AS avg_hr_bpm,
                ROUND(MAX(f.hr_max_bpm), 1) AS peak_hr_bpm,
                ROUND(AVG(f.br_avg_rpm), 1) AS avg_br_rpm,
                ROUND(AVG(f.banister_trimp), 1) AS avg_banister_trimp,
                ROUND(AVG(f.edwards_trimp), 1) AS avg_edwards_trimp,
                ROUND(AVG(f.calories_burned_kcal), 1) AS avg_calories_kcal,
                ROUND(AVG(f.rmssd_ms), 1) AS avg_rmssd_ms
            FROM fact_training_session f
            JOIN dim_sport s ON f.sport_code = s.sport_code
            GROUP BY s.sport_code, s.sport_name, s.sport_category
            ORDER BY avg_banister_trimp DESC;
        """)

        # 2. Athlete comprehensive profile and fitness load
        self.conn.execute("""
            CREATE OR REPLACE VIEW vw_athlete_summary AS
            SELECT 
                a.athlete_key,
                a.sport_code,
                s.sport_name,
                a.subject_id,
                a.gender,
                a.age_years,
                a.bmi,
                a.training_rate_weekly,
                COUNT(f.session_key) AS total_sessions_recorded,
                ROUND(SUM(f.duration_minutes), 1) AS total_training_min,
                ROUND(AVG(f.hr_avg_bpm), 1) AS overall_avg_hr,
                ROUND(MAX(f.hr_max_bpm), 1) AS overall_max_hr,
                ROUND(AVG(f.rmssd_ms), 1) AS baseline_rmssd_ms,
                ROUND(AVG(f.banister_trimp), 1) AS avg_session_trimp,
                ROUND(SUM(f.calories_burned_kcal), 1) AS total_calories_burned
            FROM dim_athlete a
            JOIN dim_sport s ON a.sport_code = s.sport_code
            LEFT JOIN fact_training_session f ON a.athlete_key = f.athlete_key
            GROUP BY a.athlete_key, a.sport_code, s.sport_name, a.subject_id, a.gender, a.age_years, a.bmi, a.training_rate_weekly
            ORDER BY a.sport_code, a.subject_id;
        """)

        # 3. High intensity ranking
        self.conn.execute("""
            CREATE OR REPLACE VIEW vw_high_intensity_sessions AS
            SELECT 
                f.session_key,
                s.sport_name,
                f.subject_id,
                f.duration_minutes,
                f.hr_avg_bpm,
                f.hr_max_bpm,
                f.banister_trimp,
                f.edwards_trimp,
                f.rmssd_ms,
                f.calories_burned_kcal
            FROM fact_training_session f
            JOIN dim_sport s ON f.sport_code = s.sport_code
            ORDER BY f.banister_trimp DESC
            LIMIT 20;
        """)

    def query(self, sql: str) -> pl.DataFrame:
        """Executes SQL query and returns Polars DataFrame."""
        return pl.from_arrow(self.conn.execute(sql).arrow())

    def close(self) -> None:
        self.conn.close()
