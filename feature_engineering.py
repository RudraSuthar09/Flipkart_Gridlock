"""
==============================================================
  Flipkart Gridlock - Full Feature Engineering & EDA Pipeline
==============================================================
  Covers:
    1. Dataset overview & shape
    2. Descriptive statistics (numeric + categorical)
    3. Missing values analysis
    4. Anomaly / outlier detection (IQR + Z-score)
    5. Correlation analysis (Pearson + Spearman + Cramér's V)
    6. Temporal feature extraction
    7. Geospatial feature engineering
    8. Categorical encoding
    9. Feature importance (Random Forest)
   10. SHAP values & plots
  Output: outputs/eda_report/ folder with CSVs + PNGs
"""

import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from scipy.stats import chi2_contingency

# ── sklearn ──────────────────────────────────────────────────────────────────
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import shap

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
OUT = "outputs/eda_report"
os.makedirs(OUT, exist_ok=True)
print(f"[INFO] Outputs -> {OUT}/")

# ─────────────────────────────────────────────────────────────────────────────
# 0.  LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/10] Loading dataset …")
df = pd.read_csv("dataset.csv", low_memory=False)
print(f"       Raw shape : {df.shape}")

# ─────────────────────────────────────────────────────────────────────────────
# 1.  OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2/10] Dataset overview …")

overview = {
    "total_rows"      : len(df),
    "total_columns"   : len(df.columns),
    "duplicate_rows"  : df.duplicated().sum(),
    "numeric_cols"    : df.select_dtypes(include=np.number).shape[1],
    "categorical_cols": df.select_dtypes(include="object").shape[1],
    "bool_cols"       : df.select_dtypes(include="bool").shape[1],
}
pd.Series(overview).to_csv(f"{OUT}/00_overview.csv")
print(pd.Series(overview))

# ─────────────────────────────────────────────────────────────────────────────
# 2.  DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/10] Descriptive statistics …")

num_cols = df.select_dtypes(include=np.number).columns.tolist()
cat_cols = df.select_dtypes(include="object").columns.tolist()

num_stats = df[num_cols].describe(percentiles=[.01,.05,.25,.5,.75,.95,.99]).T
num_stats["skewness"] = df[num_cols].skew()
num_stats["kurtosis"] = df[num_cols].kurtosis()
num_stats.to_csv(f"{OUT}/01_numeric_stats.csv")
print("\n-- Numeric Stats --")
print(num_stats.to_string())

cat_stats_rows = []
for c in cat_cols:
    s = df[c]
    cat_stats_rows.append({
        "column"     : c,
        "unique"     : s.nunique(),
        "top_value"  : s.mode()[0] if not s.mode().empty else None,
        "top_freq"   : s.value_counts().iloc[0] if not s.empty else 0,
        "top_pct"    : round(s.value_counts(normalize=True).iloc[0]*100, 2) if not s.empty else 0,
        "missing"    : s.isna().sum(),
        "missing_pct": round(s.isna().mean()*100, 2),
    })
cat_stats = pd.DataFrame(cat_stats_rows).set_index("column")
cat_stats.to_csv(f"{OUT}/02_categorical_stats.csv")
print("\n-- Categorical Stats --")
print(cat_stats.to_string())

# ─────────────────────────────────────────────────────────────────────────────
# 3.  MISSING VALUES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/10] Missing values analysis …")

miss = pd.DataFrame({
    "missing_count": df.isna().sum(),
    "missing_pct"  : round(df.isna().mean()*100, 2),
    "dtype"        : df.dtypes,
}).sort_values("missing_pct", ascending=False)
miss.to_csv(f"{OUT}/03_missing_values.csv")
print(miss[miss.missing_count > 0].to_string())

# ── Missing values heatmap
fig, ax = plt.subplots(figsize=(16, 6))
miss_pct = miss["missing_pct"].values
colors = ["#2ecc71" if v == 0 else "#e74c3c" if v > 50 else "#f39c12" for v in miss_pct]
bars = ax.bar(miss.index, miss_pct, color=colors)
ax.set_title("Missing Values (%) per Column", fontsize=14, fontweight="bold")
ax.set_xlabel("Column"); ax.set_ylabel("Missing %")
ax.set_xticklabels(miss.index, rotation=45, ha="right", fontsize=8)
ax.axhline(50, color="red", linestyle="--", alpha=0.5, label="50% threshold")
patch_ok   = mpatches.Patch(color="#2ecc71", label="0% missing")
patch_warn = mpatches.Patch(color="#f39c12", label="<50% missing")
patch_bad  = mpatches.Patch(color="#e74c3c", label=">50% missing")
ax.legend(handles=[patch_ok, patch_warn, patch_bad])
plt.tight_layout()
plt.savefig(f"{OUT}/03_missing_heatmap.png", dpi=150)
plt.close()
print(f"       Saved: 03_missing_heatmap.png")

# ─────────────────────────────────────────────────────────────────────────────
# 4.  TEMPORAL FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/10] Temporal feature engineering …")

def safe_parse(col):
    try:
        return pd.to_datetime(df[col], utc=True, errors="coerce")
    except Exception:
        return pd.NaT

df["created_dt"]  = safe_parse("created_datetime")
df["modified_dt"] = safe_parse("modified_datetime")
df["validation_dt"] = safe_parse("validation_timestamp")

ref = df["created_dt"]

df["hour"]         = ref.dt.hour
df["day_of_week"]  = ref.dt.dayofweek          # 0=Mon
df["day_name"]     = ref.dt.day_name()
df["month"]        = ref.dt.month
df["month_name"]   = ref.dt.month_name()
df["week_of_year"] = ref.dt.isocalendar().week.astype("Int64")
df["is_weekend"]   = df["day_of_week"].isin([5, 6]).astype(int)
df["is_night"]     = df["hour"].apply(lambda h: 1 if (h >= 21 or h <= 5) else 0)
df["quarter"]      = ref.dt.quarter

# Time-to-validate (seconds)
df["time_to_validate_sec"] = (df["validation_dt"] - ref).dt.total_seconds()

# Day-part
def day_part(h):
    if 5 <= h < 12:   return "Morning"
    elif 12 <= h < 17: return "Afternoon"
    elif 17 <= h < 21: return "Evening"
    else:              return "Night"

df["day_part"] = df["hour"].apply(day_part)

temp_stats = df[["hour","day_of_week","month","is_weekend","is_night","time_to_validate_sec"]].describe().T
temp_stats.to_csv(f"{OUT}/04_temporal_features.csv")
print(temp_stats.to_string())

# ── Hourly distribution
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
# Hour
df["hour"].value_counts().sort_index().plot(kind="bar", ax=axes[0], color="#3498db", edgecolor="white")
axes[0].set_title("Violations by Hour of Day", fontweight="bold"); axes[0].set_xlabel("Hour"); axes[0].set_ylabel("Count")

# Day of week
dow_labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
df["day_of_week"].value_counts().sort_index().plot(kind="bar", ax=axes[1], color="#9b59b6", edgecolor="white")
axes[1].set_xticklabels(dow_labels, rotation=0)
axes[1].set_title("Violations by Day of Week", fontweight="bold")

# Day part
dp_order = ["Morning","Afternoon","Evening","Night"]
dp_counts = df["day_part"].value_counts().reindex(dp_order, fill_value=0)
dp_counts.plot(kind="bar", ax=axes[2], color=["#f1c40f","#e67e22","#e74c3c","#2c3e50"], edgecolor="white")
axes[2].set_title("Violations by Day Part", fontweight="bold"); axes[2].set_xticklabels(dp_order, rotation=0)

plt.tight_layout()
plt.savefig(f"{OUT}/04_temporal_distribution.png", dpi=150)
plt.close()
print("       Saved: 04_temporal_distribution.png")

# Monthly trend
fig, ax = plt.subplots(figsize=(12, 4))
month_trend = df.groupby(["month","month_name"]).size().reset_index(name="count").sort_values("month")
ax.plot(month_trend["month_name"], month_trend["count"], marker="o", color="#e74c3c", linewidth=2)
ax.fill_between(range(len(month_trend)), month_trend["count"], alpha=0.15, color="#e74c3c")
ax.set_title("Monthly Violation Trend", fontweight="bold")
ax.set_ylabel("Count"); ax.set_xlabel("Month")
plt.xticks(range(len(month_trend)), month_trend["month_name"], rotation=30, ha="right")
plt.tight_layout()
plt.savefig(f"{OUT}/04b_monthly_trend.png", dpi=150)
plt.close()

# ─────────────────────────────────────────────────────────────────────────────
# 5.  GEOSPATIAL FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6/10] Geospatial features …")

df["lat_bin"] = pd.cut(df["latitude"],  bins=20)
df["lon_bin"] = pd.cut(df["longitude"], bins=20)

# Bangalore centre
B_LAT, B_LON = 12.9716, 77.5946
df["dist_from_center_km"] = np.sqrt(
    ((df["latitude"]  - B_LAT) * 111)**2 +
    ((df["longitude"] - B_LON) * 111 * np.cos(np.radians(B_LAT)))**2
)

# Hotspot density flag (top 10% distance ≡ periphery)
threshold = df["dist_from_center_km"].quantile(0.90)
df["is_periphery"] = (df["dist_from_center_km"] > threshold).astype(int)

geo_stats = df[["latitude","longitude","dist_from_center_km"]].describe().T
geo_stats.to_csv(f"{OUT}/05_geo_features.csv")
print(geo_stats.to_string())

# Scatter plot
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
sample = df.sample(min(50000, len(df)), random_state=42)
sc = axes[0].scatter(sample["longitude"], sample["latitude"],
                     c=sample["dist_from_center_km"], cmap="plasma",
                     s=1, alpha=0.4)
axes[0].set_title("Violation Locations (coloured by dist from centre)", fontweight="bold")
axes[0].set_xlabel("Longitude"); axes[0].set_ylabel("Latitude")
plt.colorbar(sc, ax=axes[0], label="dist (km)")

# Distance distribution
axes[1].hist(df["dist_from_center_km"].dropna(), bins=60, color="#1abc9c", edgecolor="white", density=True)
axes[1].set_title("Distribution of Distance from City Centre", fontweight="bold")
axes[1].set_xlabel("km"); axes[1].set_ylabel("Density")
plt.tight_layout()
plt.savefig(f"{OUT}/05_geo_scatter.png", dpi=150)
plt.close()
print("       Saved: 05_geo_scatter.png")

# ─────────────────────────────────────────────────────────────────────────────
# 6.  ANOMALY / OUTLIER DETECTION
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7/10] Anomaly & outlier detection …")

num_cols_clean = [c for c in num_cols if df[c].notna().sum() > 0]
outlier_rows = []

for col in num_cols_clean:
    s = df[col].dropna()
    # IQR
    q1, q3 = s.quantile(.25), s.quantile(.75)
    iqr = q3 - q1
    n_iqr = ((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum()
    # Z-score
    zs = np.abs(stats.zscore(s))
    n_z = (zs > 3).sum()
    outlier_rows.append({
        "column"      : col,
        "q1"          : round(q1, 4),
        "q3"          : round(q3, 4),
        "iqr"         : round(iqr, 4),
        "lower_fence" : round(q1 - 1.5*iqr, 4),
        "upper_fence" : round(q3 + 1.5*iqr, 4),
        "outliers_IQR": int(n_iqr),
        "outliers_IQR_pct": round(n_iqr/len(s)*100, 2),
        "outliers_Zscore": int(n_z),
        "outliers_Zscore_pct": round(n_z/len(s)*100, 2),
    })

outlier_df = pd.DataFrame(outlier_rows).set_index("column")
outlier_df.to_csv(f"{OUT}/06_outlier_report.csv")
print(outlier_df.to_string())

# Boxplots for numeric columns
fig, axes = plt.subplots(1, len(num_cols_clean), figsize=(4*len(num_cols_clean), 5))
if len(num_cols_clean) == 1:
    axes = [axes]
for ax, col in zip(axes, num_cols_clean):
    ax.boxplot(df[col].dropna(), vert=True, patch_artist=True,
               boxprops=dict(facecolor="#3498db", color="#2980b9"),
               medianprops=dict(color="white", linewidth=2),
               flierprops=dict(marker="o", markersize=2, alpha=0.3, color="#e74c3c"))
    ax.set_title(col, fontsize=9, fontweight="bold")
    ax.set_ylabel("Value")
plt.suptitle("Boxplots - Outlier Visualisation", fontweight="bold", fontsize=12, y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/06_boxplots.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 06_boxplots.png")

# ─────────────────────────────────────────────────────────────────────────────
# 7.  CORRELATION ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[8/10] Correlation analysis …")

# 7a. Pearson / Spearman for numerics
# Include engineered numeric cols
new_num = ["hour","day_of_week","month","is_weekend","is_night",
           "quarter","dist_from_center_km","is_periphery",
           "time_to_validate_sec"]
all_num = list(set(num_cols_clean + new_num))
num_df  = df[all_num].select_dtypes(include=np.number).dropna(how="all")

pearson  = num_df.corr(method="pearson")
spearman = num_df.corr(method="spearman")
pearson.to_csv(f"{OUT}/07a_pearson_corr.csv")
spearman.to_csv(f"{OUT}/07b_spearman_corr.csv")

fig, axes = plt.subplots(1, 2, figsize=(18, 7))
mask = np.triu(np.ones_like(pearson, dtype=bool))
sns.heatmap(pearson,  mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
            ax=axes[0], linewidths=0.5, vmin=-1, vmax=1, square=True,
            annot_kws={"size": 7})
axes[0].set_title("Pearson Correlation", fontweight="bold")

sns.heatmap(spearman, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
            ax=axes[1], linewidths=0.5, vmin=-1, vmax=1, square=True,
            annot_kws={"size": 7})
axes[1].set_title("Spearman Correlation", fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/07_correlation_heatmaps.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 07_correlation_heatmaps.png")

# 7b. Cramer's V for categoricals  (numpy-based, avoids pd.crosstab datetime inference)
def cramers_v(xarr, yarr):
    cats_x = sorted(set(xarr))
    cats_y = sorted(set(yarr))
    if len(cats_x) < 2 or len(cats_y) < 2:
        return 0.0
    xmap = {v: i for i, v in enumerate(cats_x)}
    ymap = {v: i for i, v in enumerate(cats_y)}
    ct = np.zeros((len(cats_x), len(cats_y)), dtype=int)
    for a, b in zip(xarr, yarr):
        ct[xmap[a], ymap[b]] += 1
    chi2, _, _, _ = chi2_contingency(ct)
    n = ct.sum()
    r, k = ct.shape
    return float(np.sqrt(chi2 / (n * (min(r, k) - 1) + 1e-10)))

cat_cols_fe = ["violation_type","vehicle_type","police_station","validation_status",
               "data_sent_to_scita","day_name","day_part","month_name"]
cat_cols_fe = [c for c in cat_cols_fe if c in df.columns]

cramer_data = pd.DataFrame(index=cat_cols_fe, columns=cat_cols_fe, dtype=float)
for c1 in cat_cols_fe:
    for c2 in cat_cols_fe:
        try:
            tmp = df[[c1, c2]].dropna()
            cramer_data.loc[c1, c2] = cramers_v(
                tmp[c1].astype(str).values, tmp[c2].astype(str).values)
        except Exception as e:
            print(f"       [WARN] Cramer skip {c1}x{c2}: {e}")
            cramer_data.loc[c1, c2] = 0.0

cramer_data.to_csv(f"{OUT}/07c_cramers_v.csv")
fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(cramer_data.astype(float), annot=True, fmt=".2f", cmap="YlOrRd",
            ax=ax, linewidths=0.5, vmin=0, vmax=1, square=True,
            annot_kws={"size": 8})
ax.set_title("Cramer's V - Categorical Associations", fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/07d_cramers_v_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 07d_cramers_v_heatmap.png")

# ─────────────────────────────────────────────────────────────────────────────
# 8.  CATEGORICAL VALUE DISTRIBUTIONS
# ─────────────────────────────────────────────────────────────────────────────
print("\n       Plotting categorical distributions …")

top_cats = ["violation_type", "vehicle_type", "police_station",
            "validation_status", "day_part", "day_name"]
top_cats = [c for c in top_cats if c in df.columns]

fig, axes = plt.subplots(2, 3, figsize=(20, 10))
axes = axes.flatten()
palette = sns.color_palette("tab20")

for i, col in enumerate(top_cats[:6]):
    vc = df[col].value_counts().head(15)
    axes[i].barh(vc.index[::-1], vc.values[::-1], color=palette[:len(vc)])
    axes[i].set_title(f"Top values: {col}", fontweight="bold", fontsize=10)
    axes[i].set_xlabel("Count")

for j in range(len(top_cats), 6):
    axes[j].axis("off")

plt.suptitle("Categorical Feature Distributions", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/08_categorical_distributions.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 08_categorical_distributions.png")

# ─────────────────────────────────────────────────────────────────────────────
# 9.  FEATURE IMPORTANCE — RANDOM FOREST
# ─────────────────────────────────────────────────────────────────────────────
print("\n[9/10] Feature importance (Random Forest) …")

# Target: validation_status  → binary approved / not
if "validation_status" in df.columns:
    df["target"] = (df["validation_status"] == "approved").astype(int)
else:
    # fallback: data_sent_to_scita
    df["target"] = df["data_sent_to_scita"].astype(int)

feature_cols = [
    "latitude","longitude","dist_from_center_km","is_periphery",
    "hour","day_of_week","month","is_weekend","is_night","quarter",
    "center_code",
]

# Encode key categoricals
le = LabelEncoder()
for c in ["violation_type","vehicle_type","police_station","day_part"]:
    if c in df.columns:
        df[c + "_enc"] = le.fit_transform(df[c].astype(str))
        feature_cols.append(c + "_enc")

feat_df = df[feature_cols + ["target"]].dropna()
X = feat_df[feature_cols]
y = feat_df["target"]

print(f"       Model dataset shape: {X.shape}, target balance:\n{y.value_counts()}")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2,
                                                     random_state=42, stratify=y)

rf = RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=-1,
                            random_state=42, class_weight="balanced")
rf.fit(X_train, y_train)
print("\n-- Classification Report --")
print(classification_report(y_test, rf.predict(X_test)))

importances = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
importances.to_csv(f"{OUT}/09_feature_importance.csv")
print("\n-- Feature Importances --")
print(importances.to_string())

# Plot
fig, ax = plt.subplots(figsize=(10, 7))
colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(importances)))
importances.plot(kind="barh", ax=ax, color=colors[::-1], edgecolor="white")
ax.invert_yaxis()
ax.set_title("Random Forest Feature Importances", fontweight="bold", fontsize=13)
ax.set_xlabel("Importance Score")
for bar, val in zip(ax.patches, importances.values):
    ax.text(val + 0.001, bar.get_y() + bar.get_height()/2,
            f"{val:.4f}", va="center", fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT}/09_feature_importance.png", dpi=150)
plt.close()
print("       Saved: 09_feature_importance.png")

# ─────────────────────────────────────────────────────────────────────────────
# 10. SHAP VALUES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[10/10] SHAP analysis …")

# Use a sample for speed
SHAP_SAMPLE = min(3000, len(X_test))
X_shap = X_test.sample(SHAP_SAMPLE, random_state=42)

explainer = shap.TreeExplainer(rf)
shap_values = explainer.shap_values(X_shap)

# For binary classification, use class 1 (approved)
sv = shap_values[1] if isinstance(shap_values, list) else shap_values

# ── Summary plot (beeswarm)
plt.figure(figsize=(10, 7))
shap.summary_plot(sv, X_shap, feature_names=feature_cols,
                  show=False, plot_size=(10, 7))
plt.title("SHAP Summary Plot (Beeswarm)", fontweight="bold", pad=12)
plt.tight_layout()
plt.savefig(f"{OUT}/10a_shap_beeswarm.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10a_shap_beeswarm.png")

# ── Bar summary (mean |SHAP|)
plt.figure(figsize=(10, 6))
shap.summary_plot(sv, X_shap, feature_names=feature_cols,
                  plot_type="bar", show=False)
plt.title("SHAP Feature Importance (mean |SHAP|)", fontweight="bold", pad=12)
plt.tight_layout()
plt.savefig(f"{OUT}/10b_shap_bar.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10b_shap_bar.png")

# ── Dependence plots for top 3 features
top3 = importances.head(3).index.tolist()
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, feat in zip(axes, top3):
    shap.dependence_plot(feat, sv, X_shap, feature_names=feature_cols,
                         ax=ax, show=False)
    ax.set_title(f"SHAP Dependence: {feat}", fontweight="bold", fontsize=10)
plt.tight_layout()
plt.savefig(f"{OUT}/10c_shap_dependence.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10c_shap_dependence.png")

# ── Mean SHAP magnitudes → CSV
shap_means = pd.Series(np.abs(sv).mean(axis=0), index=feature_cols).sort_values(ascending=False)
shap_means.to_csv(f"{OUT}/10_shap_importance.csv")

# ─────────────────────────────────────────────────────────────────────────────
# SAVE ENGINEERED DATASET
# ─────────────────────────────────────────────────────────────────────────────
print("\n[DONE] Saving engineered dataset …")
keep_cols = list(df.columns)
df.to_csv(f"{OUT}/engineered_dataset.csv", index=False)
print(f"       engineered_dataset.csv  →  {df.shape}")

print("\n" + "="*60)
print("  ALL DONE. Check outputs/eda_report/ for results.")
print("="*60)
