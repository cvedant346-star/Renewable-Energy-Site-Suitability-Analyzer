"""Application entry point for the site suitability analyzer UI."""

import sys
import warnings
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.main import DEFAULT_WEIGHTS, PROCESSED_DATA_PATH, build_suitability_index, cluster_regions
from src.utils import validate_weights

FACTORS = ["solar", "wind", "cloud", "humidity"]
CLUSTER_COLORS = {
    "High Potential": "#d62728",
    "Medium Potential": "#e69f00",
    "Low Potential": "#0072b2",
}

st.set_page_config(page_title="Renewable Energy Site Suitability", layout="wide")


@st.cache_data
def load_processed_regions():
    return pd.read_csv(PROCESSED_DATA_PATH)


@st.cache_data
def run_pipeline(weights):
    regions_df = load_processed_regions()
    scored_df = build_suitability_index(regions_df, weights)
    return cluster_regions(scored_df)


st.title("Renewable Energy Site Suitability Analyzer")
st.caption("5-year (2019–2023) climate baseline across 31 Indian states/UTs")

st.sidebar.header("Suitability Weights")
raw_weights = {
    "solar": st.sidebar.slider("Solar", 0.0, 1.0, DEFAULT_WEIGHTS["solar"], 0.01),
    "wind": st.sidebar.slider("Wind", 0.0, 1.0, DEFAULT_WEIGHTS["wind"], 0.01),
    "cloud": st.sidebar.slider("Cloud (lower cloud opacity = better)", 0.0, 1.0, DEFAULT_WEIGHTS["cloud"], 0.01),
    "humidity": st.sidebar.slider("Humidity (lower = better for panel efficiency)", 0.0, 1.0, DEFAULT_WEIGHTS["humidity"], 0.01),
}
raw_sum = sum(raw_weights.values())

try:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        weights = validate_weights(raw_weights, expected_factors=FACTORS)
    if caught:
        st.sidebar.info(f"Raw weights summed to {raw_sum:.2f} — auto-normalized to sum to 1.")
except ValueError as exc:
    st.sidebar.error(f"Invalid weights ({exc}). Falling back to default weights.")
    weights = DEFAULT_WEIGHTS

st.sidebar.markdown("**Normalized weights**")
for factor in FACTORS:
    st.sidebar.write(f"{factor}: {weights[factor]:.3f}")
st.sidebar.metric("Normalized weight sum", f"{sum(weights.values()):.3f}")

clustered_df = run_pipeline(weights)

st.subheader("Ranked Regions")
ranked = (
    clustered_df[["region", "suitability_score", "cluster_label", "data_quality_flag"]]
    .sort_values("suitability_score", ascending=False)
    .reset_index(drop=True)
)
ranked.index += 1
ranked.insert(
    1,
    "Flag",
    ranked["data_quality_flag"].apply(lambda flag: "⚠️ wind capped" if flag == "wind_speed_capped" else ""),
)
ranked = ranked.drop(columns=["data_quality_flag"])
st.dataframe(ranked, use_container_width=True)
st.caption(
    "⚠️ wind capped — this region's wind_speed_100m was clipped to a plausible ceiling due to "
    "corrupted source data. Its wind-based ranking relative to other ⚠️-flagged regions is not "
    "reliable; don't over-trust small score differences between them."
)

st.subheader("Top 10 Regions by Suitability Score")
top10 = ranked.head(10).sort_values("suitability_score")
fig_bar = px.bar(
    top10,
    x="suitability_score",
    y="region",
    color="cluster_label",
    color_discrete_map=CLUSTER_COLORS,
    orientation="h",
    labels={"suitability_score": "Suitability Score", "region": "Region", "cluster_label": "Cluster"},
)
st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("Solar vs. Wind Potential by Cluster")
fig_scatter = px.scatter(
    clustered_df,
    x="gti",
    y="wind_speed_100m",
    color="cluster_label",
    color_discrete_map=CLUSTER_COLORS,
    hover_name="region",
    labels={"gti": "GTI (solar potential)", "wind_speed_100m": "Wind speed @ 100m", "cluster_label": "Cluster"},
)
st.plotly_chart(fig_scatter, use_container_width=True)

with st.expander("How to read this"):
    st.markdown(
        """
- **suitability_score** (0–100) blends solar potential (GTI), wind potential (wind speed at 100m),
  cloud cover, and humidity into one number using the weights you set in the sidebar. Higher means
  more favorable overall climate conditions.
- **cluster_label** groups regions into "High / Medium / Low Potential" tiers using KMeans, based on
  the average suitability_score within each cluster.
- Cluster boundaries can be fuzzy. Under the default weighting, **Tamil Nadu** actually has the
  *highest* suitability_score of all 31 regions, yet KMeans placed it in "Medium Potential" while
  **Punjab**, scoring lower, landed in "High Potential." Similarly, **Punjab** and **HP** differ by
  less than 2 points in suitability_score but land in different tiers. In both cases the tier boundary
  fell between closely-scored regions, not because they're meaningfully different — a reminder to
  always check the numeric score, not just the tier label.
- Treat the ranking as a **relative** ordering, and treat tier labels as a rough grouping rather than
  a hard cutoff.
        """
    )

with st.expander("Limitations & Responsible Use"):
    st.markdown(
        """
- **5-year climate averages hide seasonal variation.** A region with strong annual averages may still
  have unproductive months (e.g. monsoon cloud cover, winter wind lulls) that don't show up here.
- **No land availability, grid proximity, or regulatory clearance data is included.** A high
  suitability_score reflects climate resource only, not overall project feasibility.
- **Scores are relative rankings, not investment guarantees.** They're useful for shortlisting
  candidate regions, not for financial commitments.
- **Cluster boundaries reflect KMeans' automatic grouping** and can split closely-scored regions into
  different tiers (see the Tamil Nadu/Punjab and Punjab/HP examples above). Read suitability_score
  alongside cluster_label, not in place of it.
- **Punjab's and Tamil Nadu's raw wind_speed_100m readings were corrupted at the source** (values in
  the hundreds — physically impossible at 100m hub height). `load_and_clean` clips these to a
  plausible 0-30 m/s range before averaging, but both regions still land exactly at that 30 m/s
  ceiling, so their wind scores are tied by construction and their true relative wind advantage over
  each other is not fully resolved by this fix.
        """
    )
