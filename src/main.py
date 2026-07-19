"""Entry point for the renewable energy site suitability analyzer."""

from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from preprocessing import load_and_clean
from utils import normalize_column, validate_weights

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw_energy_meteo.xlsx"
PROCESSED_DATA_PATH = PROJECT_ROOT / "data" / "processed_regions.csv"
RANKED_OUTPUT_PATH = PROJECT_ROOT / "data" / "ranked_regions.csv"

DEFAULT_WEIGHTS = {"solar": 0.4, "wind": 0.3, "cloud": 0.15, "humidity": 0.15}

# Short factor names used in weight dicts -> the raw processed_regions.csv columns they score.
FACTOR_COLUMNS = {
    "solar": "gti",
    "wind": "wind_speed_100m",
    "cloud": "cloud_opacity",
    "humidity": "relative_humidity",
}
NORM_COLUMNS = [f"norm_{factor}" for factor in FACTOR_COLUMNS]

CLUSTER_LABELS_BY_RANK = ["Low Potential", "Medium Potential", "High Potential"]


def build_suitability_index(df, weights=None):
    """Compute a 0-100 weighted suitability_score per region.

    Normalizes gti (solar factor, higher=better), wind_speed_100m (wind
    factor, higher=better), cloud_opacity (inverted, lower=better), and
    relative_humidity (inverted, lower=better for panel efficiency), then
    combines them with `weights` (short names: solar/wind/cloud/humidity)
    validated via validate_weights. Returns a copy of `df` with the
    normalized factor columns and suitability_score added.
    """
    weights = validate_weights(weights or DEFAULT_WEIGHTS, expected_factors=list(FACTOR_COLUMNS))

    df = df.copy()
    df["norm_solar"] = normalize_column(df[FACTOR_COLUMNS["solar"]])
    df["norm_wind"] = normalize_column(df[FACTOR_COLUMNS["wind"]])
    df["norm_cloud"] = normalize_column(df[FACTOR_COLUMNS["cloud"]], invert=True)
    df["norm_humidity"] = normalize_column(df[FACTOR_COLUMNS["humidity"]], invert=True)

    composite = sum(weights[factor] * df[f"norm_{factor}"] for factor in FACTOR_COLUMNS)
    df["suitability_score"] = composite * 100

    return df


def cluster_regions(df, n_clusters=3):
    """Cluster regions into potential tiers using KMeans on the normalized factors.

    Requires build_suitability_index to have already been run on `df` (uses
    its norm_* columns and suitability_score). Labels each cluster "High
    Potential" / "Medium Potential" / "Low Potential" by ranking
    cluster-average suitability_score. Returns a copy of `df` with `cluster`
    and `cluster_label` columns added.
    """
    df = df.copy()

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["cluster"] = kmeans.fit_predict(df[NORM_COLUMNS])

    cluster_scores = df.groupby("cluster")["suitability_score"].mean().sort_values()

    if n_clusters == len(CLUSTER_LABELS_BY_RANK):
        labels_by_rank = CLUSTER_LABELS_BY_RANK
    else:
        # Fall back to numbered tiers if cluster count doesn't match the 3 named tiers.
        labels_by_rank = [f"Tier {rank + 1}" for rank in range(n_clusters)]

    label_map = {cluster_id: labels_by_rank[rank] for rank, cluster_id in enumerate(cluster_scores.index)}
    df["cluster_label"] = df["cluster"].map(label_map)

    return df


def validate_clusters(df):
    """Print Spearman correlation (suitability rank vs. cluster-avg rank) and silhouette score.

    Sanity-checks that cluster_regions produced clusters that broadly agree
    with the suitability_score ranking (Spearman correlation) and that they
    are well separated (silhouette score). Requires cluster_regions to have
    already run. Returns (spearman_corr, silhouette).
    """
    cluster_avg = df.groupby("cluster")["suitability_score"].transform("mean")

    score_rank = df["suitability_score"].rank()
    cluster_avg_rank = cluster_avg.rank()

    spearman_corr, _ = spearmanr(score_rank, cluster_avg_rank)
    sil_score = silhouette_score(df[NORM_COLUMNS], df["cluster"])

    print(f"Spearman correlation (suitability rank vs. cluster-avg rank): {spearman_corr:.4f}")
    print(f"Silhouette score: {sil_score:.4f}")

    return spearman_corr, sil_score


if __name__ == "__main__":
    if RAW_DATA_PATH.exists():
        load_and_clean(RAW_DATA_PATH)  # refresh data/processed_regions.csv

    regions_df = pd.read_csv(PROCESSED_DATA_PATH)
    regions_df = build_suitability_index(regions_df, DEFAULT_WEIGHTS)
    regions_df = cluster_regions(regions_df)
    validate_clusters(regions_df)

    ranked = regions_df[["region", "suitability_score", "cluster_label", "data_quality_flag"]].sort_values(
        "suitability_score", ascending=False
    )
    ranked.to_csv(RANKED_OUTPUT_PATH, index=False)

    print(f"\nSaved ranked regions to {RANKED_OUTPUT_PATH}")
    print(ranked.to_string(index=False))
