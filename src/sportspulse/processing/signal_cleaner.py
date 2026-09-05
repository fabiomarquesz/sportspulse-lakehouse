"""
Signal Cleaning and Physiological Validation for Silver Layer.
Performs artifact removal, range validation, and signal smoothing.
"""
from typing import Dict, Any, Optional
import polars as pl
import numpy as np


class SignalCleaner:
    def __init__(
        self,
        hr_min: float = 30.0,
        hr_max: float = 240.0,
        br_min: float = 4.0,
        br_max: float = 80.0,
        rr_min: float = 250.0,
        rr_max: float = 2000.0,
    ):
        self.hr_min = hr_min
        self.hr_max = hr_max
        self.br_min = br_min
        self.br_max = br_max
        self.rr_min = rr_min
        self.rr_max = rr_max

    def clean_telemetry(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Cleans 1Hz telemetry signals:
        - Flags invalid readings
        - Replaces artifacts with nulls / bounded values
        - Computes rolling moving averages
        """
        return df.with_columns([
            # Validity flags
            (
                (pl.col("hr_bpm") >= self.hr_min) & (pl.col("hr_bpm") <= self.hr_max)
            ).alias("is_hr_valid"),
            (
                (pl.col("br_rpm") >= self.br_min) & (pl.col("br_rpm") <= self.br_max)
            ).alias("is_br_valid"),
            (
                (pl.col("rr_ms") >= self.rr_min) & (pl.col("rr_ms") <= self.rr_max)
            ).alias("is_rr_valid"),
        ]).with_columns([
            # Cleaned signals (null when invalid, then forward-filled)
            pl.when(pl.col("is_hr_valid"))
            .then(pl.col("hr_bpm"))
            .otherwise(None)
            .forward_fill()
            .backward_fill()
            .alias("hr_bpm_clean"),

            pl.when(pl.col("is_br_valid"))
            .then(pl.col("br_rpm"))
            .otherwise(None)
            .forward_fill()
            .backward_fill()
            .alias("br_rpm_clean"),

            pl.when(pl.col("is_rr_valid"))
            .then(pl.col("rr_ms"))
            .otherwise(None)
            .forward_fill()
            .backward_fill()
            .alias("rr_ms_clean"),
        ]).with_columns([
            # Rolling 5-second smoothing for stable trend analysis
            pl.col("hr_bpm_clean")
            .rolling_mean(window_size=5, min_samples=1)
            .over(["sport_code", "subject_id", "session_id"])
            .alias("hr_bpm_smoothed_5s"),

            pl.col("br_rpm_clean")
            .rolling_mean(window_size=5, min_samples=1)
            .over(["sport_code", "subject_id", "session_id"])
            .alias("br_rpm_smoothed_5s"),
        ])
