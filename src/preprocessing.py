"""Data preprocessing utilities for site suitability analysis."""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed_regions.csv"
MIN_EXPECTED_MONTHS = 60  # 5 years x 12 months

# Physically plausible bounds for columns known to contain corrupted rows in the
# source workbook: Punjab's raw air_temp is literally the YEAR value (2019-2023)
# for every month, and Punjab/Tamil Nadu have wind_speed_100m rows in the
# hundreds (a real 100m hub-height wind speed is at most ~a few dozen m/s).
# Clipping before averaging stops these rows from dominating min-max normalization
# downstream (build_suitability_index scales by column min/max).
PLAUSIBLE_RANGES = {
    "air_temp": (-25, 50),        # degrees C (HP has genuine high-altitude lows to ~-18)
    "wind_speed_100m": (0, 30),   # m/s
}


def _clip_and_report(df, column, lower, upper):
    """Clip `column` to [lower, upper], print affected regions/rows, and return the set of affected regions."""
    out_of_range = (df[column] < lower) | (df[column] > upper)
    affected_regions = set()
    if out_of_range.any():
        affected = df.loc[out_of_range].groupby("region")[column].agg(["count", "min", "max"])
        affected_regions = set(affected.index)
        print(f"Clipped {column} to [{lower}, {upper}] — {int(out_of_range.sum())} row(s) affected:")
        for region, row in affected.iterrows():
            print(f"  {region}: {int(row['count'])} row(s), original range [{row['min']:.2f}, {row['max']:.2f}]")
    df[column] = df[column].clip(lower, upper)
    return df, affected_regions


def load_and_clean(path):
    """Load the raw state-level energy/meteo workbook and build a per-region climate baseline.

    Reads the single-sheet Excel file at `path`, drops the junk "Unnamed: 22"
    column and any other fully-null columns, normalizes the region name
    column, clips known-corrupted columns (see PLAUSIBLE_RANGES) to a
    physically plausible range, and averages every numeric measurement
    across all available year/month records per region into a single
    5-year baseline row. Also counts months_of_data per region (before
    aggregating) so incomplete regions can be flagged, and adds a
    data_quality_flag column marking regions whose wind_speed_100m was
    clipped ("wind_speed_capped") so their relative wind ranking against
    other capped regions isn't over-trusted. Writes the result to
    data/processed_regions.csv and returns it as a DataFrame.
    """
    df = pd.read_excel(path)

    df = df.drop(columns=["Unnamed: 22"], errors="ignore")
    df = df.dropna(axis=1, how="all")

    df = df.rename(columns={"Name of State/UT": "region"})
    df["region"] = df["region"].str.strip()

    # Some measurement columns (e.g. wind) contain stray blank/text cells that
    # make pandas infer them as object dtype; coerce so they aggregate as numbers.
    measurement_cols = [col for col in df.columns if col not in ("region", "YEAR", "MONTH")]
    df[measurement_cols] = df[measurement_cols].apply(pd.to_numeric, errors="coerce")

    wind_capped_regions = set()
    for column, (lower, upper) in PLAUSIBLE_RANGES.items():
        df, affected_regions = _clip_and_report(df, column, lower, upper)
        if column == "wind_speed_100m":
            wind_capped_regions = affected_regions

    numeric_cols = [
        col for col in df.select_dtypes(include="number").columns
        if col not in ("YEAR", "MONTH")
    ]

    months_of_data = df.groupby("region").size().rename("months_of_data")
    aggregated = df.groupby("region")[numeric_cols].mean()
    aggregated = aggregated.join(months_of_data).reset_index()

    # Regions whose wind_speed_100m was clipped have an unrecoverable true wind
    # ranking relative to each other (both got capped to the same ceiling), so
    # flag them rather than let the suitability model imply a clean ranking.
    aggregated["data_quality_flag"] = aggregated["region"].apply(
        lambda region: "wind_speed_capped" if region in wind_capped_regions else ""
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    aggregated.to_csv(OUTPUT_PATH, index=False)

    incomplete = aggregated[aggregated["months_of_data"] < MIN_EXPECTED_MONTHS]

    print(f"Rows: {len(aggregated)}")
    print(f"Columns: {list(aggregated.columns)}")
    if incomplete.empty:
        print(f"All regions have >= {MIN_EXPECTED_MONTHS} months of data.")
    else:
        print(f"Regions with months_of_data < {MIN_EXPECTED_MONTHS}:")
        for _, row in incomplete.iterrows():
            print(f"  {row['region']}: {int(row['months_of_data'])}")

    return aggregated


if __name__ == "__main__":
    load_and_clean(PROJECT_ROOT / "data" / "raw_energy_meteo.xlsx")
