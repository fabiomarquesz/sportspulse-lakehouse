"""
Training Phase Alignment Engine for Silver Layer.
Synchronizes 1Hz telemetry with protocol phases (Resting, Warm-up, Exercise, Recovery).
"""
from typing import Dict, Any, List, Optional
import polars as pl


PHASE_CATEGORY_MAP = {
    "resting": "Rest",
    "resting phase": "Rest",
    "wu": "Warmup",
    "warmup": "Warmup",
    "initial phase": "Warmup",
    "initial flat phase": "Warmup",
    "recovery": "Recovery",
    "recovery phase": "Recovery",
    "final phase": "Recovery",
    "final flat phase": "Recovery",
    "exercise": "Main_Workout",
    "exercise phase": "Main_Workout",
    "central phase": "Main_Workout",
    "wod": "Main_Workout",
    "skill": "Technical_Skill",
    "treadmill": "Main_Workout",
    "cyclette": "Main_Workout",
    "uphill phase": "High_Intensity_Interval",
    "downhill phase": "Active_Recovery",
}


def categorize_phase(phase_name: Optional[str]) -> str:
    """Classifies granular exercise names into standardized physiological phase categories."""
    if not phase_name:
        return "Unknown"
    norm = phase_name.lower().strip()
    if norm in PHASE_CATEGORY_MAP:
        return PHASE_CATEGORY_MAP[norm]
    if "squat" in norm or "press" in norm or "extension" in norm or "machine" in norm:
        return "Resistance_Exercise"
    if "rest" in norm:
        return "Rest"
    if "recov" in norm:
        return "Recovery"
    return "Main_Workout"


def align_telemetry_with_phases(
    df_telemetry: pl.DataFrame,
    df_phases: pl.DataFrame,
) -> pl.DataFrame:
    """
    Assigns phase_name, phase_category, and phase_elapsed_sec to every 1-second telemetry record.
    Uses range matching against active phases for each session.
    """
    # Filter active phases with valid start/end bounds
    active_phases = df_phases.filter(
        pl.col("is_active") & pl.col("start_time_sec").is_not_null() & pl.col("end_time_sec").is_not_null()
    )

    # Convert to Python dict lookup for blazing fast alignment per session
    phase_lookup: Dict[str, List[Dict[str, Any]]] = {}
    for row in active_phases.iter_rows(named=True):
        key = f"{row['sport_code']}_{row['subject_id']}_{row['session_id']}"
        if key not in phase_lookup:
            phase_lookup[key] = []
        phase_lookup[key].append({
            "phase_name": row["phase_name"],
            "start_sec": row["start_time_sec"],
            "end_sec": row["end_time_sec"],
            "phase_category": categorize_phase(row["phase_name"]),
        })

    # Vectorized matching via Polars struct mapping / function
    def match_phase_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
        key = f"{row_dict['sport_code']}_{row_dict['subject_id']}_{row_dict['session_id']}"
        t = row_dict["time_sec"]
        phases = phase_lookup.get(key, [])
        for p in phases:
            if p["start_sec"] <= t < p["end_sec"]:
                return {
                    "phase_name": p["phase_name"],
                    "phase_category": p["phase_category"],
                    "phase_elapsed_sec": t - p["start_sec"],
                }
        return {
            "phase_name": "Unspecified / Exercise",
            "phase_category": "Main_Workout",
            "phase_elapsed_sec": t,
        }

    # Extract columns as list of dicts for session phase alignment
    # Or join via sql/conditional expressions
    phase_names = []
    phase_categories = []
    phase_elapsed = []

    for sport, subj, sess, t in zip(
        df_telemetry["sport_code"].to_list(),
        df_telemetry["subject_id"].to_list(),
        df_telemetry["session_id"].to_list(),
        df_telemetry["time_sec"].to_list(),
    ):
        key = f"{sport}_{subj}_{sess}"
        phases = phase_lookup.get(key, [])
        matched = False
        for p in phases:
            if p["start_sec"] <= t < p["end_sec"]:
                phase_names.append(p["phase_name"])
                phase_categories.append(p["phase_category"])
                phase_elapsed.append(t - p["start_sec"])
                matched = True
                break
        if not matched:
            phase_names.append("General_Activity")
            phase_categories.append("Main_Workout")
            phase_elapsed.append(t)

    return df_telemetry.with_columns([
        pl.Series("phase_name", phase_names, dtype=pl.String),
        pl.Series("phase_category", phase_categories, dtype=pl.String),
        pl.Series("phase_elapsed_sec", phase_elapsed, dtype=pl.Int32),
    ])
