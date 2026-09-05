"""
Unit tests for Bronze layer parsers.
"""
from pathlib import Path
import pytest
import polars as pl
from sportspulse.ingestion.mat_parser import parse_mat_file
from sportspulse.ingestion.metadata_parser import parse_dem_file, parse_trnote_file

SAMPLE_MAT = "/mnt/dados/Downloads/SportDB/AER/S1/CRD1/Data.mat"
SAMPLE_DEM = "/mnt/dados/Downloads/SportDB/AER/S1/CRD1/Dem.txt"
SAMPLE_TR = "/mnt/dados/Downloads/SportDB/AER/S1/CRD1/TrNote.txt"


def test_parse_mat_file():
    bio = parse_mat_file(SAMPLE_MAT, "AER", "S1", "CRD1")
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


def test_parse_dem_file():
    df_dem = parse_dem_file(SAMPLE_DEM, "AER", "S1", "CRD1")
    assert isinstance(df_dem, pl.DataFrame)
    assert df_dem.shape[0] == 1
    assert "gender" in df_dem.columns
    assert "bmi" in df_dem.columns
    assert df_dem["age_years"][0] == 24


def test_parse_trnote_file():
    df_tr = parse_trnote_file(SAMPLE_TR, "AER", "S1", "CRD1")
    assert isinstance(df_tr, pl.DataFrame)
    assert df_tr.shape[0] >= 3
    phases = df_tr["phase_name"].to_list()
    assert "Resting" in phases
    assert "Exercise" in phases
    assert "Recovery" in phases
