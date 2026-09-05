"""
Star Schema Dimensional Model Builder for Gold Layer.
Transforms enriched Silver data into analytical Dimension and Fact tables.
"""

from typing import Any

import numpy as np
import polars as pl

from sportspulse.analytics.hrv_metrics import compute_time_domain_hrv
from sportspulse.analytics.trimp import (
    compute_banister_trimp,
    compute_edwards_trimp,
    estimate_calories_burned,
)


def build_star_schema(
    df_silver_telemetry: pl.DataFrame,
    df_silver_athletes: pl.DataFrame,
    sports_cfg: dict[str, Any],
) -> dict[str, pl.DataFrame]:
    """
    Builds the complete Star Schema model:
    - Dimensions: dim_athlete, dim_sport, dim_phase
    - Facts: fact_training_session, fact_session_phase, fact_telemetry_1s
    """
    # 1. Dimension: dim_sport
    sports_records = []
    for code, info in sports_cfg.items():
        sports_records.append(
            {
                "sport_code": code,
                "sport_name": info.get("name", code),
                "sport_category": info.get("category", "General"),
                "sport_description": info.get("description", ""),
            }
        )
    dim_sport = pl.DataFrame(sports_records)

    # 2. Dimension: dim_athlete
    dim_athlete = df_silver_athletes.select(
        [
            pl.concat_str([pl.col("sport_code"), pl.lit("_"), pl.col("subject_id")]).alias("athlete_key"),
            pl.col("sport_code"),
            pl.col("subject_id"),
            pl.col("gender"),
            pl.col("age_years"),
            pl.col("weight_kg"),
            pl.col("height_cm"),
            pl.col("bmi"),
            pl.col("is_smoker"),
            pl.col("drinks_alcohol"),
            pl.col("training_rate_weekly"),
        ]
    )

    # 3. Dimension: dim_phase
    dim_phase = pl.DataFrame(
        {
            "phase_category": [
                "Rest",
                "Warmup",
                "Main_Workout",
                "Technical_Skill",
                "Resistance_Exercise",
                "High_Intensity_Interval",
                "Active_Recovery",
                "Recovery",
                "Unknown",
            ],
            "phase_description": [
                "Período de repouso basal ou pré-treino",
                "Aquecimento cardiovascular e articular",
                "Bloco principal de treinamento ou WOD",
                "Treino técnico de habilidades específicas",
                "Exercícios de musculação e sobrecarga",
                "Tiros e estímulos de alta intensidade",
                "Descanso ativo ou transição",
                "Período de recuperação e volta à calma",
                "Fase não classificada",
            ],
        }
    )

    # 4. Fact: fact_training_session & fact_session_phase
    session_keys = (
        df_silver_telemetry.select(["sport_code", "subject_id", "session_id"])
        .unique()
        .sort(["sport_code", "subject_id", "session_id"])
    )

    fact_session_rows = []
    fact_phase_rows = []

    for row in session_keys.iter_rows(named=True):
        sp = row["sport_code"]
        sb = row["subject_id"]
        ss = row["session_id"]
        sess_df = df_silver_telemetry.filter(
            (pl.col("sport_code") == sp) & (pl.col("subject_id") == sb) & (pl.col("session_id") == ss)
        )

        n_sec = len(sess_df)
        dur_min = round(n_sec / 60.0, 2)

        hr_clean = sess_df["hr_bpm_clean"].to_numpy()
        br_clean = sess_df["br_rpm_clean"].to_numpy()
        rr_clean = sess_df["rr_ms_clean"].to_numpy()

        hr_avg = float(np.nanmean(hr_clean)) if len(hr_clean) > 0 else 0.0
        hr_max = float(np.nanmax(hr_clean)) if len(hr_clean) > 0 else 0.0
        hr_min = float(np.nanmin(hr_clean)) if len(hr_clean) > 0 else 0.0
        br_avg = float(np.nanmean(br_clean)) if len(br_clean) > 0 else 0.0
        br_max = float(np.nanmax(br_clean)) if len(br_clean) > 0 else 0.0

        hr_rest = float(sess_df["hr_rest_est"][0]) if sess_df["hr_rest_est"][0] is not None else 60.0
        hr_max_est = float(sess_df["hr_max_est"][0]) if sess_df["hr_max_est"][0] is not None else 190.0
        gender = sess_df["gender"][0]
        is_female = bool(gender == "Female")
        weight_kg = sess_df["weight_kg"][0]
        age_years = sess_df["age_years"][0]

        # HRV Metrics
        hrv_dict = compute_time_domain_hrv(rr_clean)

        # TRIMP Models
        banister_trimp = compute_banister_trimp(
            duration_min=dur_min,
            hr_avg=hr_avg,
            hr_rest=hr_rest,
            hr_max=hr_max_est,
            is_female=is_female,
        )
        edwards_trimp = compute_edwards_trimp(hr_clean, hr_max_est)
        calories = estimate_calories_burned(
            duration_min=dur_min,
            hr_avg=hr_avg,
            weight_kg=weight_kg,
            age_years=age_years,
            is_female=is_female,
        )

        session_key = f"{sp}_{sb}_{ss}"
        athlete_key = f"{sp}_{sb}"

        fact_session_rows.append(
            {
                "session_key": session_key,
                "athlete_key": athlete_key,
                "sport_code": sp,
                "subject_id": sb,
                "session_id": ss,
                "duration_seconds": n_sec,
                "duration_minutes": dur_min,
                "hr_avg_bpm": round(hr_avg, 1),
                "hr_max_bpm": round(hr_max, 1),
                "hr_min_bpm": round(hr_min, 1),
                "hr_rest_bpm": round(hr_rest, 1),
                "hr_max_est_bpm": round(hr_max_est, 1),
                "br_avg_rpm": round(br_avg, 1),
                "br_max_rpm": round(br_max, 1),
                "rmssd_ms": hrv_dict["rmssd_ms"],
                "sdnn_ms": hrv_dict["sdnn_ms"],
                "pnn50_pct": hrv_dict["pnn50_pct"],
                "banister_trimp": banister_trimp,
                "edwards_trimp": edwards_trimp,
                "calories_burned_kcal": calories,
            }
        )

        # Phase breakdowns
        phases_in_sess = sess_df.group_by(["phase_name", "phase_category"]).agg(
            [
                pl.len().alias("phase_sec"),
                pl.col("hr_bpm_clean").mean().alias("phase_hr_avg"),
                pl.col("hr_bpm_clean").max().alias("phase_hr_max"),
                pl.col("br_rpm_clean").mean().alias("phase_br_avg"),
            ]
        )

        for p_row in phases_in_sess.iter_rows(named=True):
            p_dur_min = round(p_row["phase_sec"] / 60.0, 2)
            p_hr = p_row["phase_hr_avg"] or 0.0
            p_trimp = compute_banister_trimp(
                duration_min=p_dur_min,
                hr_avg=p_hr,
                hr_rest=hr_rest,
                hr_max=hr_max_est,
                is_female=is_female,
            )
            fact_phase_rows.append(
                {
                    "session_key": session_key,
                    "athlete_key": athlete_key,
                    "sport_code": sp,
                    "subject_id": sb,
                    "session_id": ss,
                    "phase_name": p_row["phase_name"],
                    "phase_category": p_row["phase_category"],
                    "duration_seconds": p_row["phase_sec"],
                    "duration_minutes": p_dur_min,
                    "hr_avg_bpm": round(p_hr, 1),
                    "hr_max_bpm": round(p_row["phase_hr_max"] or 0.0, 1),
                    "br_avg_rpm": round(p_row["phase_br_avg"] or 0.0, 1),
                    "phase_banister_trimp": p_trimp,
                }
            )

    fact_training_session = pl.DataFrame(fact_session_rows)
    fact_session_phases = pl.DataFrame(fact_phase_rows)

    # 5. Fact: fact_telemetry_1s
    fact_telemetry_1s = df_silver_telemetry.select(
        [
            pl.concat_str(
                [pl.col("sport_code"), pl.lit("_"), pl.col("subject_id"), pl.lit("_"), pl.col("session_id")]
            ).alias("session_key"),
            pl.concat_str([pl.col("sport_code"), pl.lit("_"), pl.col("subject_id")]).alias("athlete_key"),
            pl.col("sport_code"),
            pl.col("subject_id"),
            pl.col("session_id"),
            pl.col("time_sec"),
            pl.col("phase_name"),
            pl.col("phase_category"),
            pl.col("hr_bpm_clean").alias("hr_bpm"),
            pl.col("hr_bpm_smoothed_5s"),
            pl.col("br_rpm_clean").alias("br_rpm"),
            pl.col("rr_ms_clean").alias("rr_ms"),
            pl.col("hr_reserve_pct"),
            pl.col("hr_br_coupling_ratio"),
        ]
    )

    return {
        "dim_sport": dim_sport,
        "dim_athlete": dim_athlete,
        "dim_phase": dim_phase,
        "fact_training_session": fact_training_session,
        "fact_session_phases": fact_session_phases,
        "fact_telemetry_1s": fact_telemetry_1s,
    }
