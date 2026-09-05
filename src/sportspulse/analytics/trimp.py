"""
Training Impulse (TRIMP) Calculation Engine for Gold Layer.
Implements Banister's TRIMP (exponential physiological strain) and Edwards' Zone-based TRIMP.
"""

import numpy as np


def compute_banister_trimp(
    duration_min: float,
    hr_avg: float,
    hr_rest: float,
    hr_max: float,
    is_female: bool = False,
) -> float:
    """
    Computes Banister's TRIMP (Training Impulse):
    TRIMP = Duration (min) * DeltaHR * b * exp(a * DeltaHR)
    where DeltaHR = (HR - HR_rest) / (HR_max - HR_rest)
    For Males: a = 1.92, b = 0.64
    For Females: a = 1.67, b = 0.86
    """
    if duration_min <= 0 or hr_max <= hr_rest:
        return 0.0

    delta_hr = np.clip((hr_avg - hr_rest) / (hr_max - hr_rest), 0.0, 1.0)

    a = 1.67 if is_female else 1.92
    b = 0.86 if is_female else 0.64

    trimp_val = duration_min * delta_hr * b * np.exp(a * delta_hr)
    return round(float(trimp_val), 2)


def compute_edwards_trimp(
    hr_series: np.ndarray,
    hr_max: float,
) -> float:
    """
    Computes Edwards' TRIMP accumulating time spent in 5 heart rate intensity zones:
    Zone 1: 50% - 60% HRmax -> weight 1
    Zone 2: 60% - 70% HRmax -> weight 2
    Zone 3: 70% - 80% HRmax -> weight 3
    Zone 4: 80% - 90% HRmax -> weight 4
    Zone 5: 90% - 100% HRmax -> weight 5
    """
    if len(hr_series) == 0 or hr_max <= 0:
        return 0.0

    hr_ratio = hr_series / hr_max

    # Time in minutes per second sample (1/60 min)
    dt_min = 1.0 / 60.0

    z1 = np.sum((hr_ratio >= 0.50) & (hr_ratio < 0.60)) * dt_min * 1
    z2 = np.sum((hr_ratio >= 0.60) & (hr_ratio < 0.70)) * dt_min * 2
    z3 = np.sum((hr_ratio >= 0.70) & (hr_ratio < 0.80)) * dt_min * 3
    z4 = np.sum((hr_ratio >= 0.80) & (hr_ratio < 0.90)) * dt_min * 4
    z5 = np.sum(hr_ratio >= 0.90) * dt_min * 5

    total_edwards = z1 + z2 + z3 + z4 + z5
    return round(float(total_edwards), 2)


def estimate_calories_burned(
    duration_min: float,
    hr_avg: float,
    weight_kg: float | None = 70.0,
    age_years: int | None = 25,
    is_female: bool = False,
) -> float:
    """
    Estimates energetic expenditure (kcal) based on Keytel et al. formula (2005).
    """
    w = weight_kg if weight_kg and weight_kg > 0 else 70.0
    a = age_years if age_years and age_years > 0 else 25

    if is_female:
        # Female formula: ((-20.4022 + (0.4472 * HR) - (0.1263 * Weight) + (0.074 * Age)) / 4.184) * Duration_min
        kcal = ((-20.4022 + (0.4472 * hr_avg) - (0.1263 * w) + (0.074 * a)) / 4.184) * duration_min
    else:
        # Male formula: ((-55.0969 + (0.6309 * HR) + (0.1988 * Weight) + (0.2017 * Age)) / 4.184) * Duration_min
        kcal = ((-55.0969 + (0.6309 * hr_avg) + (0.1988 * w) + (0.2017 * a)) / 4.184) * duration_min

    return round(max(0.0, float(kcal)), 1)
