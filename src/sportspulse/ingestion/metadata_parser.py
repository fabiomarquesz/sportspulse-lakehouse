"""
Metadata Parser for SportDB (Dem.txt and TrNote.txt).
Extracts demographic attributes and training phase time intervals with explicit schema enforcement.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
import polars as pl


DEMOGRAPHICS_SCHEMA = {
    "sport_code": pl.String,
    "subject_id": pl.String,
    "session_id": pl.String,
    "sex_code": pl.Int32,
    "gender": pl.String,
    "age_years": pl.Int32,
    "weight_kg": pl.Float64,
    "height_cm": pl.Float64,
    "bmi": pl.Float64,
    "is_smoker": pl.Boolean,
    "drinks_alcohol": pl.Boolean,
    "training_rate_weekly": pl.Float64,
}

TRAINING_PHASES_SCHEMA = {
    "sport_code": pl.String,
    "subject_id": pl.String,
    "session_id": pl.String,
    "phase_name": pl.String,
    "start_time_str": pl.String,
    "end_time_str": pl.String,
    "start_time_sec": pl.Int32,
    "end_time_sec": pl.Int32,
    "duration_sec": pl.Int32,
    "is_active": pl.Boolean,
    "notes": pl.String,
}


def time_str_to_seconds(time_str: str) -> int:
    """Converts HH:MM:SS string to total seconds."""
    parts = time_str.strip().split(":")
    if len(parts) == 3:
        h, m, s = map(int, parts)
        return h * 3600 + m * 60 + s
    elif len(parts) == 2:
        m, s = map(int, parts)
        return m * 60 + s
    return 0


def clean_val(val: str) -> Optional[float]:
    """Helper to convert numeric strings or 'NA' to Optional[float]."""
    val = val.strip().replace("\ufeff", "")
    if not val or val.upper() in ("NA", "NAN", "NULL", "NONE", "-"):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_dem_file(file_path: Path | str, sport_code: str, subject_id: str, session_id: str) -> pl.DataFrame:
    """
    Parses Dem.txt containing athlete demographic attributes.
    Header: Sex, Age, Weight, Height, Smoker, Alcool, Training_Rate
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dem.txt not found: {path}")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip().replace("\ufeff", "") for line in f if line.strip()]

    if not lines:
        raise ValueError(f"Dem.txt is empty: {path}")

    header = [h.strip() for h in lines[0].split("\t")]
    if len(lines) > 1:
        values = [v.strip() for v in lines[1].split("\t")]
    else:
        values = ["NA"] * len(header)

    while len(values) < len(header):
        values.append("NA")

    row_dict = dict(zip(header, values))

    sex_raw = clean_val(row_dict.get("Sex", "NA"))
    sex_desc = "Male" if sex_raw == 1.0 else ("Female" if sex_raw == 2.0 else "Unknown")
    
    age = clean_val(row_dict.get("Age", "NA"))
    weight = clean_val(row_dict.get("Weight", "NA"))
    height = clean_val(row_dict.get("Height", "NA"))
    smoker = clean_val(row_dict.get("Smoker", "NA"))
    alcool = clean_val(row_dict.get("Alcool", "NA"))
    training_rate = clean_val(row_dict.get("Training_Rate", "NA"))

    bmi = None
    if weight and height and height > 0:
        bmi = round(weight / ((height / 100.0) ** 2), 2)

    data = {
        "sport_code": [sport_code],
        "subject_id": [subject_id],
        "session_id": [session_id],
        "sex_code": [int(sex_raw) if sex_raw is not None else None],
        "gender": [sex_desc],
        "age_years": [int(age) if age is not None else None],
        "weight_kg": [float(weight) if weight is not None else None],
        "height_cm": [float(height) if height is not None else None],
        "bmi": [float(bmi) if bmi is not None else None],
        "is_smoker": [bool(smoker == 1.0) if smoker is not None else None],
        "drinks_alcohol": [bool(alcool == 1.0) if alcool is not None else None],
        "training_rate_weekly": [float(training_rate) if training_rate is not None else None],
    }

    return pl.DataFrame(data, schema=DEMOGRAPHICS_SCHEMA)


def parse_trnote_file(file_path: Path | str, sport_code: str, subject_id: str, session_id: str) -> pl.DataFrame:
    """
    Parses TrNote.txt extracting training phases and raw notes.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"TrNote.txt not found: {path}")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip().replace("\ufeff", "") for line in f if line.strip()]

    phase_pattern = re.compile(
        r"^([A-Za-z0-9_\s\-\(\)]+?)\s*:\s*(?:from\s*)?(\d{1,2}:\d{2}:\d{2})\s+to\s+(\d{1,2}:\d{2}:\d{2})",
        re.IGNORECASE,
    )
    none_pattern = re.compile(r"^([A-Za-z0-9_\s\-\(\)]+?)\s*:\s*(?:none|null|na)", re.IGNORECASE)

    records: List[Dict[str, Any]] = []
    
    for line in lines:
        m_phase = phase_pattern.search(line)
        m_none = none_pattern.search(line)

        if m_phase:
            phase_name = m_phase.group(1).strip()
            start_str = m_phase.group(2).strip()
            end_str = m_phase.group(3).strip()
            
            start_sec = time_str_to_seconds(start_str)
            end_sec = time_str_to_seconds(end_str)
            duration_sec = max(0, end_sec - start_sec)
            
            records.append({
                "sport_code": sport_code,
                "subject_id": subject_id,
                "session_id": session_id,
                "phase_name": phase_name,
                "start_time_str": start_str,
                "end_time_str": end_str,
                "start_time_sec": start_sec,
                "end_time_sec": end_sec,
                "duration_sec": duration_sec,
                "is_active": True,
                "notes": line,
            })
        elif m_none:
            phase_name = m_none.group(1).strip()
            records.append({
                "sport_code": sport_code,
                "subject_id": subject_id,
                "session_id": session_id,
                "phase_name": phase_name,
                "start_time_str": None,
                "end_time_str": None,
                "start_time_sec": None,
                "end_time_sec": None,
                "duration_sec": 0,
                "is_active": False,
                "notes": line,
            })

    if not records:
        full_text = " | ".join(lines) if lines else "None"
        records.append({
            "sport_code": sport_code,
            "subject_id": subject_id,
            "session_id": session_id,
            "phase_name": "Full Session",
            "start_time_str": None,
            "end_time_str": None,
            "start_time_sec": 0,
            "end_time_sec": None,
            "duration_sec": None,
            "is_active": True,
            "notes": full_text,
        })

    return pl.DataFrame(records, schema=TRAINING_PHASES_SCHEMA)
