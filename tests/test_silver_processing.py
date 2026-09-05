"""
Unit tests for Silver layer cleaning and phase alignment.
"""
import polars as pl
import pytest
from sportspulse.processing.signal_cleaner import SignalCleaner
from sportspulse.processing.phase_aligner import categorize_phase, align_telemetry_with_phases


def test_signal_cleaner_filtering():
    df = pl.DataFrame({
        "sport_code": ["RUN", "RUN", "RUN"],
        "subject_id": ["S1", "S1", "S1"],
        "session_id": ["CRD1", "CRD1", "CRD1"],
        "time_sec": [0, 1, 2],
        "hr_bpm": [20.0, 150.0, 260.0],  # 20 and 260 are invalid
        "br_rpm": [15.0, 2.0, 20.0],      # 2 is invalid
        "rr_ms": [100.0, 800.0, 2500.0],  # 100 and 2500 are invalid
    })

    cleaner = SignalCleaner(hr_min=30, hr_max=240, br_min=4, br_max=80, rr_min=250, rr_max=2000)
    cleaned = cleaner.clean_telemetry(df)

    assert "is_hr_valid" in cleaned.columns
    assert "hr_bpm_clean" in cleaned.columns
    assert cleaned["is_hr_valid"].to_list() == [False, True, False]
    assert cleaned["is_br_valid"].to_list() == [True, False, True]
    assert cleaned["is_rr_valid"].to_list() == [False, True, False]


def test_phase_categorization():
    assert categorize_phase("Resting") == "Rest"
    assert categorize_phase("WU") == "Warmup"
    assert categorize_phase("WOD") == "Main_Workout"
    assert categorize_phase("Recovery") == "Recovery"
    assert categorize_phase("Leg Press") == "Resistance_Exercise"


def test_align_telemetry_with_phases():
    df_telemetry = pl.DataFrame({
        "sport_code": ["CRO", "CRO", "CRO"],
        "subject_id": ["S1", "S1", "S1"],
        "session_id": ["CRD1", "CRD1", "CRD1"],
        "time_sec": [10, 70, 150],
        "hr_bpm": [70.0, 140.0, 80.0],
        "br_rpm": [12.0, 30.0, 14.0],
        "rr_ms": [850.0, 420.0, 750.0],
    })

    df_phases = pl.DataFrame({
        "sport_code": ["CRO", "CRO"],
        "subject_id": ["S1", "S1"],
        "session_id": ["CRD1", "CRD1"],
        "phase_name": ["WU", "WOD"],
        "start_time_str": ["00:00:00", "00:01:00"],
        "end_time_str": ["00:01:00", "00:03:00"],
        "start_time_sec": [0, 60],
        "end_time_sec": [60, 180],
        "duration_sec": [60, 120],
        "is_active": [True, True],
        "notes": ["Warmup", "Workout of the day"],
    })

    aligned = align_telemetry_with_phases(df_telemetry, df_phases)
    assert "phase_name" in aligned.columns
    assert "phase_category" in aligned.columns
    assert aligned["phase_name"].to_list() == ["WU", "WOD", "WOD"]
    assert aligned["phase_category"].to_list() == ["Warmup", "Main_Workout", "Main_Workout"]
