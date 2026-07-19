# Renewable Energy Site Suitability Analyzer — Project Report

**Author:** Vedant Chaudhary (solo project)

## 1. Problem

Deciding where to build a new solar or wind project requires weighing several climate variables at once — solar irradiance, wind speed, cloud cover, humidity — across many candidate regions and years of monthly records. Doing this comparison by eye across 31 Indian states/UTs and 5 years of monthly data is slow, inconsistent, and easy to get wrong. This project builds a repeatable, adjustable pipeline that turns raw climate data into a single **suitability score** per region, groups regions into potential tiers, and exposes both through an interactive dashboard.

## 2. Users & Stakeholders

- **Renewable energy planners / site selection teams**, who need a fast first-pass shortlist of candidate regions before commissioning detailed feasibility studies.
- **Investors and developers**, who want to compare regions under different strategic priorities (e.g. "we're a solar-first fund" vs. "we're evaluating a hybrid project") without re-running an analysis from scratch.
- **Policy / regulatory bodies**, who might use regional rankings to prioritize grid infrastructure or incentive programs.

The tool is explicitly a **screening aid**, not a final investment decision-maker — it deliberately excludes land, grid, and regulatory data (see Limitations) so it stays scoped to climate suitability.

## 3. Dataset

**Source:** Kaggle — *Renewable Energy and Meteorological Data of India*.

The raw file is a **5-year, monthly** dataset (2019–2023, 1,859 rows) covering **31 Indian states/UTs**, with:
- Solar variables: GTI, DNI, GHI, clearsky DHI/DNI/GTI, cloud opacity, albedo
- Wind variable: wind speed at 100m (turbine hub height)
- General meteorological variables: air temperature, relative humidity, surface pressure, precipitation rate
- Renewable generation potential columns: wind, solar, biomass, hydro

This project aggregates the monthly records down to **one row per region** — a 5-year climate baseline — via `src/preprocessing.py::load_and_clean`. Each region's row also carries a `months_of_data` count (to flag incomplete records) and a `data_quality_flag` (to flag known source-data corruption; see Section 6).

## 4. Methodology

1. **Load & clean** (`preprocessing.py`): read the raw Excel file, drop the junk `Unnamed: 22` column, coerce stray text/blank cells to numeric, clip two known-corrupted columns to physically plausible ranges (see Section 6), and aggregate to one row per region by averaging every numeric measurement across all available months.
2. **Build the suitability index** (`main.py::build_suitability_index`): min-max normalize four factors to 0–1 — solar (GTI, higher = better), wind (wind speed @ 100m, higher = better), cloud opacity (inverted, lower = better), and relative humidity (inverted, lower = better for panel efficiency) — then combine them into a single 0–100 `suitability_score` using a user-adjustable weight profile. Weights are validated and auto-normalized to sum to 1 (`utils.py::validate_weights`).
3. **Cluster regions** (`main.py::cluster_regions`): run KMeans on the same four normalized factors to group regions into "High / Medium / Low Potential" tiers, with tier labels assigned by ranking each cluster's average `suitability_score`.
4. **Validate the clustering** (`main.py::validate_clusters`): compute the Spearman correlation between each region's suitability rank and its cluster's average rank (checks internal consistency) and the silhouette score (checks how well-separated the clusters actually are), so the tiers are never presented as more authoritative than the data supports.
5. **Scenario testing**: re-run the suitability index under alternative weight profiles (solar-heavy, wind-heavy) to see which regions are robust across priorities vs. which are single-resource bets.
6. **Dashboard**: an interactive Streamlit app exposes all of the above with live weight sliders, a ranked table, charts, and plain-English explanations of the score, clusters, and their limitations.

## 5. Results

**Default weighting** (40% solar / 30% wind / 15% cloud / 15% humidity). Top 10 regions by `suitability_score`:

| Rank | Region | Suitability Score | Cluster |
|---|---|---|---|
| 1 | Tamil Nadu | 68.63 | Medium Potential |
| 2 | Punjab | 58.64 | High Potential |
| 3 | HP | 57.08 | Medium Potential |
| 4 | Rajasthan | 56.31 | Medium Potential |
| 5 | Gujarat | 52.43 | Medium Potential |
| 6 | Karnataka | 47.95 | Medium Potential |
| 7 | Uttarakhand | 45.82 | Medium Potential |
| 8 | J & K | 45.72 | Medium Potential |
| 9 | Madhya Pradesh | 45.50 | Medium Potential |
| 10 | Maharashtra | 45.40 | Medium Potential |

Cluster validation: **Spearman correlation = 0.8743** (tiers are internally consistent with the underlying scores), **silhouette score = 0.3351** (moderate cluster separation — meaningful groupings, but with real fuzziness at the boundaries).

**A deliberate, disclosed score/cluster mismatch:** Tamil Nadu has the single *highest* `suitability_score` of all 31 regions (68.63) yet KMeans placed it in "Medium Potential," while Punjab — scoring lower (58.64) — landed in "High Potential." This isn't a bug being hidden; it's flagged directly in the app and notebook as a reminder that KMeans tiers are a rough grouping, not a strict ranking, and the numeric score should always be checked alongside the tier label.

**Scenario sensitivity (solar-heavy vs. wind-heavy weighting).** Re-running the index under a solar-heavy profile (60% solar / 15% wind / 15% cloud / 10% humidity) and a wind-heavy profile (15% solar / 60% wind / 15% cloud / 10% humidity) reveals which regions are resource-specific bets vs. genuinely balanced:

- **HP** tops the solar-heavy ranking (#1) but drops to **#10** under wind-heavy weighting.
- **Punjab** shows the mirror pattern: it falls to **#19** under solar-heavy weighting but climbs back to **#2** under wind-heavy weighting — its overall ranking is being driven by wind, not solar.
- **Karnataka, Madhya Pradesh, and Maharashtra** stay consistently mid-pack (ranks roughly 5–10) across all three weighting scenarios — these are the most balanced, lowest-risk candidates regardless of which resource an investor prioritizes.

## 6. A Data Quality Discovery Made Mid-Project

While testing the dashboard, the wind-vs-solar scatter plot was found to be unreadable — one point sat far outside the rest of the data. Investigation traced this to **corrupted raw source data**: Punjab's raw `wind_speed_100m` averaged **977.7 m/s** (physically impossible — real 100m hub-height wind speeds are typically single digits) and Punjab's raw `air_temp` was **literally the `YEAR` value** (2019–2023) for every month, consistent with a column-shift error in the source spreadsheet for that region's rows. Tamil Nadu's `wind_speed_100m` was also corrupted (averaging 163.9 m/s).

Because `normalize_column` performs min-max scaling, a single corrupted extreme value redefines the column's max and crushes every other region's normalized wind score toward zero — this had been silently inflating Punjab's ranking (and, by extension, distorting every result) for the entire project up to that point.

**Fix:** `load_and_clean` now clips `wind_speed_100m` to a physically plausible `[0, 30]` m/s range and `air_temp` to `[-25, 50]` °C *before* averaging (the lower `air_temp` bound was deliberately widened from an initial `-10` after checking that HP has genuine high-altitude winter lows down to -18°C — the clip must not remove real data). Every clipped row is logged with the affected region and its original value range. A new **`data_quality_flag`** column marks Punjab and Tamil Nadu as `"wind_speed_capped"` in both `processed_regions.csv` and `ranked_regions.csv`, and the Streamlit app surfaces this as a **⚠️ wind capped** marker directly in the ranked table with an explanatory caption — because both regions are now tied at the same clip ceiling, their true relative wind advantage over each other is unrecoverable from the source file, and the app makes sure a user can't over-trust that specific comparison.

## 7. Limitations

- **Wind-speed-capped regions have an unrecoverable true ranking.** Punjab and Tamil Nadu are both clipped to the same 30 m/s ceiling; the fix prevents them from distorting everyone else's scores, but their ranking *relative to each other* cannot be recovered from the corrupted source file.
- **5-year averages hide seasonal variation.** A region with strong annual averages may still have unproductive months (e.g. monsoon cloud cover, winter wind lulls) that don't show up in a single yearly baseline.
- **No land availability, grid proximity, or regulatory clearance data is included.** A high `suitability_score` reflects climate resource only, not overall project feasibility.
- **Meghalaya has only 59 of the expected 60 months of data** (flagged via `months_of_data`), a minor but real gap in its 5-year baseline.
- **Latitude/longitude coordinates are duplicated across regions.** Only 29 unique lat/long pairs exist across 31 regions in the raw file (e.g. two different states share identical coordinates), a source-data issue that would affect any downstream geospatial/mapping work, even though it doesn't affect the current suitability scoring.
- **Scores are relative rankings, not investment guarantees**, and cluster boundaries can split closely-scored regions into different tiers (see Section 5).

## 8. Future Improvements

- Go back to the original data provider to recover true `wind_speed_100m` values for Punjab and Tamil Nadu, and correct the duplicated latitude/longitude pairs, rather than clipping/tolerating them.
- Bring in land availability, grid/transmission proximity, and regulatory/permitting data to move from climate suitability toward true project feasibility.
- Score at a finer time resolution (seasonal or monthly) instead of a single 5-year average, so seasonal risk is visible per region.
- Try alternative clustering approaches (e.g. hierarchical clustering, or letting the number of clusters vary) and compare against KMeans.
- Incorporate the existing but currently unused `solar`/`wind`/`biomass`/`hydro` generation-potential columns into a multi-technology suitability comparison.
