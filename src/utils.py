"""Shared helper functions for the site suitability analyzer."""

import warnings

import pandas as pd

# Suitability-scoring factors, kept in sync with the variables profiled in
# notebooks/exploration_or_modeling.ipynb.
EXPECTED_FACTORS = {
    "gti",
    "dni",
    "ghi",
    "wind_speed_100m",
    "air_temp",
    "cloud_opacity",
    "relative_humidity",
}


def normalize_column(series: pd.Series, invert: bool = False) -> pd.Series:
    """Min-max scale a numeric Series to the 0-1 range.

    Set invert=True for factors where a lower raw value is more suitable
    (e.g. cloud_opacity, extreme air_temp), so the output always means
    "higher is better" regardless of the underlying factor's direction.
    """
    min_val = series.min()
    max_val = series.max()

    if max_val == min_val:
        # No variation to scale against — every region is equally (neutrally) suitable.
        scaled = pd.Series(0.5, index=series.index)
    else:
        scaled = (series - min_val) / (max_val - min_val)

    return 1 - scaled if invert else scaled


def validate_weights(weights: dict, expected_factors=EXPECTED_FACTORS) -> dict:
    """Validate a {factor_name: weight} dict for the suitability scoring model.

    `expected_factors` may be any iterable of names (e.g. a set or list) —
    it doesn't have to match raw DataFrame column names, just whatever
    keys the caller's weights dict is supposed to use.

    Raises ValueError if any key doesn't match an expected factor name (a
    typo'd or unknown factor is a configuration bug, not something to
    silently paper over). If the weights don't sum to 1, emits a warning
    and returns an auto-normalized copy; otherwise returns the weights
    unchanged.
    """
    expected_factors = set(expected_factors)
    given_keys = set(weights)
    unexpected = given_keys - expected_factors
    missing = expected_factors - given_keys

    if unexpected or missing:
        problems = []
        if unexpected:
            problems.append(f"unexpected keys {sorted(unexpected)}")
        if missing:
            problems.append(f"missing keys {sorted(missing)}")
        raise ValueError(
            f"weights keys do not match expected factors ({'; '.join(problems)}). "
            f"Expected factors: {sorted(expected_factors)}"
        )

    total = sum(weights.values())
    if total == 0:
        raise ValueError("weights sum to 0 — cannot normalize.")

    if abs(total - 1.0) > 1e-9:
        warnings.warn(f"weights sum to {total}, not 1 — auto-normalizing.", stacklevel=2)
        return {key: value / total for key, value in weights.items()}

    return dict(weights)
