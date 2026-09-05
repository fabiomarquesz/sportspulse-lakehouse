"""
Unit tests for Bronze layer parsers (supports CI and local environments).
"""

from pathlib import Path

import numpy as np
import polars as pl
import pytest
import scipy.io as sio

from sportspulse.ingestion.mat_parser import parse_mat_file
from sportspulse.ingestion.metadata_parser import parse_dem_file, parse_trnote_file

SAMPLE_MAT = Path("/mnt/dados/Downloads/SportDB/AER/S1/CRD1/Data.mat")
SAMPLE_DEM = Path("/mnt/dados/Downloads/SportDB/AER/S1/CRD1/Dem.txt")
SAMPLE_TR = Path("/mnt/dados/Downloads/SportDB/AER/S1/CRD1/TrNote.txt")


@pytest.fixture
def mock_session_dir(tmp_path):
    """Creates a temporary synthetic SportDB session directory for CI testing."""
    crd_dir = tmp_path / "AER" / "S1" / "CRD1"
    crd_dir.mkdir(parents=True)

    # 1. Synthetic MAT file
    n_sec = 60
    hr = np.full((n_sec, 1), 75, dtype=np.uint8)
    rr = np.full((n_sec, 1), 800.0, dtype=np.float64)
    br = np.full((n_sec, 1), 16.0, dtype=np.float64)
    ecg = np.full((n_sec * 250, 1), 1.25, dtype=np.float64)

    mat_struct = {
        "Data": np.array(
            [[(hr, rr, br, ecg)]],
            dtype=[("HR", "O"), ("RR", "O"), ("BR", "O"), ("ECG", "O")],
        )
    }
    mat_path = crd_dir / "Data.mat"
    sio.savemat(str(mat_path), mat_struct)

    # 2. Synthetic Dem.txt
    dem_path = crd_dir / "Dem.txt"
    dem_path.write_text("Sex\tAge\tWeight\tHeight\tSmoker\tAlcool\tTraining_Rate\n1\t24\t70.0\t175.0\t0\t0\t4.0\n")

    # 3. Synthetic TrNote.txt
    tr_path = crd_dir / "TrNote.txt"
    tr_path.write_text(
        "Resting: from 00:00:00 to 00:00:20\nExercise: from 00:00:20 to 00:00:50\nRecovery: from 00:00:50 to 00:01:00\n"
    )

    return crd_dir


def test_parse_mat_file(mock_session_dir):
    mat_path = SAMPLE_MAT if SAMPLE_MAT.exists() else mock_session_dir / "Data.mat"
    bio = parse_mat_file(mat_path, "AER", "S1", "CRD1")
    assert bio.sport_code == "AER"
    assert bio.subject_id == "S1"
    assert bio.session_id == "CRD1"
    assert len(bio.hr) > 0
    assert len(bio.rr) == len(bio.hr)
    assert len(bio.br) == len(bio.hr)
    assert len(bio.ecg) == len(bio.hr) * 250

    df_1hz = bio.to_1hz_dataframe()
    assert isinstance(df_1hz, pl.DataFrame)
    assert df_1hz.shape[0] == len(bio.hr)
    assert "hr_bpm" in df_1hz.columns
    assert "rr_ms" in df_1hz.columns
    assert "br_rpm" in df_1hz.columns


def test_parse_dem_file(mock_session_dir):
    dem_path = SAMPLE_DEM if SAMPLE_DEM.exists() else mock_session_dir / "Dem.txt"
    df_dem = parse_dem_file(dem_path, "AER", "S1", "CRD1")
    assert isinstance(df_dem, pl.DataFrame)
    assert df_dem.shape[0] == 1
    assert "gender" in df_dem.columns
    assert "bmi" in df_dem.columns
    assert df_dem["age_years"][0] == 24


def test_parse_trnote_file(mock_session_dir):
    tr_path = SAMPLE_TR if SAMPLE_TR.exists() else mock_session_dir / "TrNote.txt"
    df_tr = parse_trnote_file(tr_path, "AER", "S1", "CRD1")
    assert isinstance(df_tr, pl.DataFrame)
    assert df_tr.shape[0] >= 3
    phases = df_tr["phase_name"].to_list()
    assert "Resting" in phases
    assert "Exercise" in phases
    assert "Recovery" in phases
