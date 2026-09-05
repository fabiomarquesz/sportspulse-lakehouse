"""
Unit tests for Gold layer HRV, TRIMP, and Star Schema calculations.
"""

import numpy as np
import pytest

from sportspulse.analytics.hrv_metrics import compute_time_domain_hrv
from sportspulse.analytics.trimp import (
    compute_banister_trimp,
    compute_edwards_trimp,
    estimate_calories_burned,
)


def test_compute_time_domain_hrv():
    # Synthetic RR intervals around 1000ms with some variation
    rr = np.array([1000.0, 1020.0, 980.0, 1010.0, 990.0, 1030.0, 970.0])
    hrv = compute_time_domain_hrv(rr)

    assert hrv["mean_rr_ms"] is not None
    assert 950.0 < hrv["mean_rr_ms"] < 1050.0
    assert hrv["sdnn_ms"] is not None and hrv["sdnn_ms"] > 0
    assert hrv["rmssd_ms"] is not None and hrv["rmssd_ms"] > 0
    assert hrv["pnn50_pct"] is not None


def test_compute_banister_trimp():
    # High intensity session vs low intensity session
    trimp_high = compute_banister_trimp(duration_min=60, hr_avg=170, hr_rest=60, hr_max=190, is_female=False)
    trimp_low = compute_banister_trimp(duration_min=60, hr_avg=110, hr_rest=60, hr_max=190, is_female=False)

    assert trimp_high > trimp_low
    assert trimp_high > 50.0


def test_compute_edwards_trimp():
    # 600 samples (10 minutes) in Zone 4 (85% of HRmax)
    hr_max = 200.0
    hr_series = np.full(600, 170.0)  # 170 / 200 = 0.85 -> Zone 4 (weight 4)
    edwards = compute_edwards_trimp(hr_series, hr_max)

    # 10 minutes * weight 4 = 40 TRIMP points
    assert pytest.approx(edwards, rel=0.1) == 40.0


def test_estimate_calories_burned():
    kcal = estimate_calories_burned(duration_min=60, hr_avg=150, weight_kg=75.0, age_years=25, is_female=False)
    assert kcal > 300.0
