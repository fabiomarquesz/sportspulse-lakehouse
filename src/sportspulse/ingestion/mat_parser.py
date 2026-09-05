"""
MATLAB .mat File Parser for Cardiorespiratory Signals (SportDB).
Extracts HR (1Hz), RR (1Hz), BR (1Hz), and ECG (250Hz).
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
import scipy.io as sio


@dataclass
class BiosignalData:
    sport_code: str
    subject_id: str
    session_id: str
    duration_seconds: int
    hr: np.ndarray  # 1 Hz, uint8/float
    rr: np.ndarray  # 1 Hz, float (ms)
    br: np.ndarray  # 1 Hz, float (rpm)
    ecg: np.ndarray  # 250 Hz, float (mV)
    ecg_sampling_rate: int = 250
    telemetry_sampling_rate: int = 1

    def to_1hz_dataframe(self) -> pl.DataFrame:
        """Converts 1Hz telemetries (HR, RR, BR) into a Polars DataFrame."""
        n_samples = len(self.hr)
        time_sec = np.arange(n_samples, dtype=np.int32)

        return pl.DataFrame(
            {
                "sport_code": [self.sport_code] * n_samples,
                "subject_id": [self.subject_id] * n_samples,
                "session_id": [self.session_id] * n_samples,
                "time_sec": time_sec,
                "hr_bpm": self.hr.astype(np.float32),
                "rr_ms": self.rr.astype(np.float32),
                "br_rpm": self.br.astype(np.float32),
            }
        )

    def to_ecg_dataframe(self) -> pl.DataFrame:
        """Converts 250Hz ECG signal into a Polars DataFrame with sample indices and timestamps."""
        n_samples = len(self.ecg)
        sample_idx = np.arange(n_samples, dtype=np.int64)
        time_sec = sample_idx / float(self.ecg_sampling_rate)

        return pl.DataFrame(
            {
                "sport_code": [self.sport_code] * n_samples,
                "subject_id": [self.subject_id] * n_samples,
                "session_id": [self.session_id] * n_samples,
                "sample_idx": sample_idx,
                "time_sec": time_sec.astype(np.float32),
                "ecg_mv": self.ecg.astype(np.float32),
            }
        )


def parse_mat_file(file_path: Path | str, sport_code: str, subject_id: str, session_id: str) -> BiosignalData:
    """
    Parses a Data.mat file from SportDB and extracts all cardiorespiratory signals.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"MAT file not found: {path}")

    mat = sio.loadmat(str(path))
    if "Data" not in mat:
        raise ValueError(f"Expected 'Data' key in {path}, found: {list(mat.keys())}")

    data = mat["Data"][0, 0]

    # Extract arrays
    hr = data["HR"].flatten()
    rr = data["RR"].flatten()
    br = data["BR"].flatten()
    ecg = data["ECG"].flatten()

    duration = len(hr)

    return BiosignalData(
        sport_code=sport_code,
        subject_id=subject_id,
        session_id=session_id,
        duration_seconds=duration,
        hr=hr,
        rr=rr,
        br=br,
        ecg=ecg,
        ecg_sampling_rate=250,
        telemetry_sampling_rate=1,
    )
