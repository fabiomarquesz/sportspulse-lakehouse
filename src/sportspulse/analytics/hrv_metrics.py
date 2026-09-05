"""
Heart Rate Variability (HRV) Analysis Engine for Gold Layer.
Computes standard time-domain autonomic nervous system markers (RMSSD, SDNN, pNN50).
"""

import numpy as np


def compute_time_domain_hrv(rr_intervals_ms: np.ndarray) -> dict[str, float | None]:
    """
    Computes standard time-domain HRV metrics from an array of valid RR intervals (in ms).
    - SDNN: Standard deviation of NN/RR intervals (general autonomic tone)
    - RMSSD: Root Mean Square of Successive Differences (parasympathetic/vagal tone)
    - pNN50: Percentage of successive intervals differing by > 50ms
    - mean_rr: Mean RR interval in ms
    """
    # Filter out nulls and invalid physiological values (250ms <= RR <= 2000ms)
    valid_rr = rr_intervals_ms[(~np.isnan(rr_intervals_ms)) & (rr_intervals_ms >= 250.0) & (rr_intervals_ms <= 2000.0)]

    if len(valid_rr) < 5:
        return {
            "mean_rr_ms": None,
            "sdnn_ms": None,
            "rmssd_ms": None,
            "pnn50_pct": None,
            "valid_rr_count": len(valid_rr),
        }

    mean_rr = float(np.mean(valid_rr))
    sdnn = float(np.std(valid_rr, ddof=1)) if len(valid_rr) > 1 else 0.0

    # Successive differences: RR_{i+1} - RR_i
    diff_rr = np.diff(valid_rr)
    rmssd = float(np.sqrt(np.mean(diff_rr**2))) if len(diff_rr) > 0 else 0.0

    # pNN50: percentage of differences > 50 ms
    nn50_count = int(np.sum(np.abs(diff_rr) > 50.0))
    pnn50 = float((nn50_count / len(diff_rr)) * 100.0) if len(diff_rr) > 0 else 0.0

    return {
        "mean_rr_ms": round(mean_rr, 2),
        "sdnn_ms": round(sdnn, 2),
        "rmssd_ms": round(rmssd, 2),
        "pnn50_pct": round(pnn50, 2),
        "valid_rr_count": len(valid_rr),
    }
