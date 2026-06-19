"""
=============================================================
  Flipkart Gridlock — EDA Completion + Distribution Plots
=============================================================
  Resumes from stage 7b (Pearson/Spearman already saved).
  Runs:
    7c/7d  Cramér's V heatmap
    08     Categorical distributions
    09     Random Forest feature importance
    10     SHAP beeswarm / bar / dependence
    11     Full distribution plots (hist + KDE, all features)
    12     Violin / box split by target
    SAVE   engineered_dataset.csv
"""

import os, warnings, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
from scipy.stats import chi2_contingency
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import shap

warnings.filterwarnings("ignore")

OUT = "outputs/eda_report"
os.makedirs(OUT, exist_ok=True)

PALETTE_MAIN   = "#3b82f6"
PALETTE_SECOND = "#f97316"
PALETTE_GRAD   = "viridis"

t0 = time.time()

# ─────────────────────────────────────────────────────────────────────────────
# 0. LOAD & REBUILD FEATURES
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("[LOAD] Loading dataset …")
df = pd.read_csv("dataset.csv", low_memory=False)
print(f"       shape : {df.shape}")

def safe_parse(col):
    return pd.to_datetime(df[col], utc=True, errors="coerce")

df["created_dt"]    = safe_parse("created_datetime")
df["validation_dt"] = safe_parse("validation_timestamp")
ref = df["created_dt"]

df["hour"]                = ref.dt.hour
df["day_of_week"]         = ref.dt.dayofweek
df["day_name"]            = ref.dt.day_name()
df["month"]               = ref.dt.month
df["month_name"]          = ref.dt.month_name()
df["week_of_year"]        = ref.dt.isocalendar().week.astype("Int64")
df["is_weekend"]          = df["day_of_week"].isin([5, 6]).astype(int)
df["quarter"]             = ref.dt.quarter
df["time_to_validate_sec"]= (df["validation_dt"] - ref).dt.total_seconds()

def day_part(h):
    if   5 <= h < 12:  return "Morning"
    elif 12 <= h < 17: return "Afternoon"
    elif 17 <= h < 21: return "Evening"
    else:              return "Night"
df["day_part"] = df["hour"].apply(day_part)

def is_night(h):
    return 1 if (h >= 21 or h <= 5) else 0
df["is_night"] = df["hour"].apply(is_night)

B_LAT, B_LON = 12.9716, 77.5946
df["dist_from_center_km"] = np.sqrt(
    ((df["latitude"]  - B_LAT) * 111) ** 2 +
    ((df["longitude"] - B_LON) * 111 * np.cos(np.radians(B_LAT))) ** 2
)
thr = df["dist_from_center_km"].quantile(0.90)
df["is_periphery"] = (df["dist_from_center_km"] > thr).astype(int)

print(f"       Features rebuilt. ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 7c / 7d  CRAMÉR'S V
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7c] Cramér's V …")

def cramers_v(xarr, yarr):
    cats_x = sorted(set(xarr));  cats_y = sorted(set(yarr))
    if len(cats_x) < 2 or len(cats_y) < 2: return 0.0
    xmap = {v: i for i, v in enumerate(cats_x)}
    ymap = {v: i for i, v in enumerate(cats_y)}
    ct   = np.zeros((len(cats_x), len(cats_y)), dtype=int)
    for a, b in zip(xarr, yarr): ct[xmap[a], ymap[b]] += 1
    chi2, _, _, _ = chi2_contingency(ct)
    n = ct.sum(); r, k = ct.shape
    return float(np.sqrt(chi2 / (n * (min(r, k) - 1) + 1e-10)))

cat_cols_fe = ["violation_type", "vehicle_type", "police_station",
               "validation_status", "day_name", "day_part", "month_name"]
cat_cols_fe = [c for c in cat_cols_fe if c in df.columns]

cramer_data = pd.DataFrame(index=cat_cols_fe, columns=cat_cols_fe, dtype=float)
for c1 in cat_cols_fe:
    for c2 in cat_cols_fe:
        try:
            tmp = df[[c1, c2]].dropna()
            cramer_data.loc[c1, c2] = cramers_v(
                tmp[c1].astype(str).values, tmp[c2].astype(str).values)
        except Exception as e:
            cramer_data.loc[c1, c2] = 0.0

cramer_data.to_csv(f"{OUT}/07c_cramers_v.csv")

fig, ax = plt.subplots(figsize=(11, 9))
sns.heatmap(cramer_data.astype(float), annot=True, fmt=".2f", cmap="YlOrRd",
            ax=ax, linewidths=0.6, vmin=0, vmax=1, square=True,
            annot_kws={"size": 9})
ax.set_title("Cramér's V — Categorical Associations", fontweight="bold", fontsize=13, pad=14)
plt.xticks(rotation=30, ha="right"); plt.yticks(rotation=0)
plt.tight_layout()
plt.savefig(f"{OUT}/07d_cramers_v_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 07c_cramers_v.csv + 07d_cramers_v_heatmap.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 08  CATEGORICAL DISTRIBUTIONS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[08] Categorical distributions …")

top_cats = ["violation_type", "vehicle_type", "police_station",
            "validation_status", "day_part", "day_name"]
top_cats = [c for c in top_cats if c in df.columns]

pal20 = sns.color_palette("tab20")
fig, axes = plt.subplots(2, 3, figsize=(22, 11))
axes = axes.flatten()

for i, col in enumerate(top_cats[:6]):
    vc = df[col].value_counts().head(15)
    axes[i].barh(vc.index[::-1], vc.values[::-1], color=pal20[:len(vc)], edgecolor="white")
    axes[i].set_title(f"Top values — {col}", fontweight="bold", fontsize=11)
    axes[i].set_xlabel("Count", fontsize=9)
    for y_pos, val in enumerate(vc.values[::-1]):
        axes[i].text(val + vc.values.max() * 0.01, y_pos,
                     f"{val:,}", va="center", fontsize=7.5, color="#333")

for j in range(len(top_cats), 6):
    axes[j].axis("off")

plt.suptitle("Categorical Feature Distributions", fontsize=15, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/08_categorical_distributions.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 08_categorical_distributions.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 09  RANDOM FOREST FEATURE IMPORTANCE
# ─────────────────────────────────────────────────────────────────────────────
print("\n[09] Random Forest feature importance …")

df["target"] = (df["validation_status"] == "approved").astype(int)

feature_cols = [
    "latitude", "longitude", "dist_from_center_km", "is_periphery",
    "hour", "day_of_week", "month", "is_weekend", "is_night", "quarter",
    "center_code",
]
le = LabelEncoder()
for c in ["violation_type", "vehicle_type", "police_station", "day_part"]:
    if c in df.columns:
        df[c + "_enc"] = le.fit_transform(df[c].astype(str))
        feature_cols.append(c + "_enc")

feat_df = df[feature_cols + ["target"]].dropna()
X = feat_df[feature_cols];  y = feat_df["target"]
print(f"       Model set: {X.shape}  |  target balance:\n{y.value_counts()}")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

rf = RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=-1,
                             random_state=42, class_weight="balanced")
rf.fit(X_train, y_train)
print("\n-- Classification Report --")
print(classification_report(y_test, rf.predict(X_test)))

importances = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
importances.to_csv(f"{OUT}/09_feature_importance.csv")

fig, ax = plt.subplots(figsize=(11, 7))
colors_imp = plt.cm.viridis(np.linspace(0.2, 0.9, len(importances)))
importances.plot(kind="barh", ax=ax, color=colors_imp[::-1], edgecolor="white")
ax.invert_yaxis()
ax.set_title("Random Forest — Feature Importances", fontweight="bold", fontsize=13)
ax.set_xlabel("Importance Score")
for bar, val in zip(ax.patches, importances.values):
    ax.text(val + 0.001, bar.get_y() + bar.get_height() / 2,
            f"{val:.4f}", va="center", fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT}/09_feature_importance.png", dpi=150)
plt.close()
print(f"       Saved: 09_feature_importance.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 10  SHAP ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[10] SHAP analysis …")

SHAP_SAMPLE = min(3000, len(X_test))
X_shap = X_test.sample(SHAP_SAMPLE, random_state=42)

explainer   = shap.TreeExplainer(rf)
shap_values = explainer.shap_values(X_shap)
sv = shap_values[1] if isinstance(shap_values, list) else shap_values

# Beeswarm
plt.figure(figsize=(10, 7))
shap.summary_plot(sv, X_shap, feature_names=feature_cols, show=False, plot_size=(10, 7))
plt.title("SHAP Summary Plot (Beeswarm)", fontweight="bold", pad=12)
plt.tight_layout()
plt.savefig(f"{OUT}/10a_shap_beeswarm.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10a_shap_beeswarm.png")

# Bar
plt.figure(figsize=(10, 6))
shap.summary_plot(sv, X_shap, feature_names=feature_cols, plot_type="bar", show=False)
plt.title("SHAP Feature Importance (mean |SHAP|)", fontweight="bold", pad=12)
plt.tight_layout()
plt.savefig(f"{OUT}/10b_shap_bar.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10b_shap_bar.png")

# Dependence plots — top 3 features
top3 = importances.head(3).index.tolist()
fig, axes_dep = plt.subplots(1, 3, figsize=(19, 5))
for ax_d, feat in zip(axes_dep, top3):
    shap.dependence_plot(feat, sv, X_shap, feature_names=feature_cols,
                         ax=ax_d, show=False)
    ax_d.set_title(f"SHAP Dependence: {feat}", fontweight="bold", fontsize=10)
plt.tight_layout()
plt.savefig(f"{OUT}/10c_shap_dependence.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10c_shap_dependence.png")

shap_means = pd.Series(np.abs(sv).mean(axis=0), index=feature_cols).sort_values(ascending=False)
shap_means.to_csv(f"{OUT}/10_shap_importance.csv")
print(f"       Saved: 10_shap_importance.csv  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11  COMPREHENSIVE DISTRIBUTION PLOTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11] Distribution plots for all features …")

# ── 11a  NUMERIC FEATURES — Histogram + KDE + stats
numeric_feats = {
    "latitude"              : "Latitude",
    "longitude"             : "Longitude",
    "center_code"           : "Center Code",
    "hour"                  : "Hour of Day",
    "day_of_week"           : "Day of Week (0=Mon)",
    "month"                 : "Month",
    "quarter"               : "Quarter",
    "dist_from_center_km"   : "Distance from City Centre (km)",
    "time_to_validate_sec"  : "Time to Validate (seconds)",
}

n_num = len(numeric_feats)
ncols = 3
nrows = int(np.ceil(n_num / ncols))

fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 5 * nrows))
axes = axes.flatten()

cmap_list = plt.cm.tab10(np.linspace(0, 0.9, n_num))

for idx, (col, label) in enumerate(numeric_feats.items()):
    ax = axes[idx]
    if col not in df.columns:
        ax.axis("off"); continue

    series = df[col].dropna()
    color  = cmap_list[idx]

    # Cap extreme values for time_to_validate to make plot readable
    if col == "time_to_validate_sec":
        series = series[(series >= 0) & (series < series.quantile(0.99))]

    # Histogram
    n_bins = min(60, series.nunique())
    ax.hist(series, bins=n_bins, color=color, edgecolor="white",
            alpha=0.75, density=True, label="Histogram")

    # KDE overlay
    try:
        kde = stats.gaussian_kde(series.sample(min(20000, len(series)), random_state=42))
        xs  = np.linspace(series.min(), series.max(), 300)
        ax.plot(xs, kde(xs), color="white", linewidth=2.5, zorder=3)
        ax.plot(xs, kde(xs), color=color,   linewidth=1.5, linestyle="--", zorder=4, label="KDE")
    except Exception:
        pass

    # Vertical lines: mean, median
    ax.axvline(series.mean(),   color="#ef4444", linewidth=1.5, linestyle="--", label=f"Mean={series.mean():.2f}")
    ax.axvline(series.median(), color="#22c55e", linewidth=1.5, linestyle=":",  label=f"Median={series.median():.2f}")

    # Stats box
    sk = series.skew(); ku = series.kurtosis()
    ax.set_title(f"{label}", fontweight="bold", fontsize=11, pad=6)
    ax.set_xlabel(label, fontsize=9)
    ax.set_ylabel("Density", fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    ax.text(0.02, 0.97,
            f"n={len(series):,}\nSkew={sk:.2f}\nKurt={ku:.2f}\nStd={series.std():.2f}",
            transform=ax.transAxes, fontsize=7.5, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))
    ax.set_facecolor("#1e293b")
    fig.patch.set_facecolor("#0f172a")

for j in range(n_num, len(axes)):
    axes[j].axis("off")

plt.suptitle("Numeric Feature Distributions — Histogram + KDE",
             fontsize=16, fontweight="bold", color="white", y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/11a_numeric_distributions.png", dpi=150, bbox_inches="tight",
            facecolor="#0f172a")
plt.close()
plt.rcParams.update(plt.rcParamsDefault)   # reset dark bg
print("       Saved: 11a_numeric_distributions.png")

# ── 11b  BINARY / FLAG FEATURES — Donut charts
flag_feats = {
    "is_weekend" : ["Weekday", "Weekend"],
    "is_night"   : ["Daytime", "Night"],
    "is_periphery": ["Central", "Periphery"],
}

fig, axes = plt.subplots(1, 3, figsize=(18, 6))
donut_colors = [["#3b82f6", "#f97316"], ["#8b5cf6", "#f59e0b"], ["#10b981", "#ef4444"]]
for idx, (col, labels) in enumerate(flag_feats.items()):
    ax = axes[idx]
    if col not in df.columns: ax.axis("off"); continue
    counts = df[col].value_counts().sort_index()
    wedges, texts, autotexts = ax.pie(
        counts, labels=labels, autopct="%1.1f%%",
        colors=donut_colors[idx], startangle=90,
        wedgeprops=dict(width=0.5, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=12))
    for at in autotexts: at.set_fontsize(11); at.set_fontweight("bold")
    ax.set_title(f"{col}", fontweight="bold", fontsize=13)
    ax.text(0, 0, f"n={len(df):,}", ha="center", va="center",
            fontsize=10, fontweight="bold", color="#444")

plt.suptitle("Binary / Flag Feature Distributions (Donut Charts)",
             fontsize=15, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(f"{OUT}/11b_binary_features.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 11b_binary_features.png")

# ── 11c  TEMPORAL HEATMAP — Hour × Day-of-Week violation density
print("       Building hourly heatmap …")
pivot = (df.groupby(["day_of_week", "hour"])
           .size()
           .reset_index(name="count")
           .pivot(index="day_of_week", columns="hour", values="count")
           .fillna(0))

day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
fig, ax = plt.subplots(figsize=(18, 5))
sns.heatmap(pivot, cmap="YlOrRd", ax=ax, linewidths=0.3,
            yticklabels=day_labels, annot=False,
            cbar_kws={"label": "Violation Count"})
ax.set_title("Violation Intensity — Hour of Day × Day of Week",
             fontweight="bold", fontsize=13, pad=10)
ax.set_xlabel("Hour of Day", fontsize=10)
ax.set_ylabel("Day of Week", fontsize=10)
plt.tight_layout()
plt.savefig(f"{OUT}/11c_hourly_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 11c_hourly_heatmap.png")

# ── 11d  VIOLIN PLOTS — numeric features split by is_weekend
print("       Building violin plots …")
violin_feats = ["hour", "dist_from_center_km", "month"]
violin_feats = [c for c in violin_feats if c in df.columns]

fig, axes = plt.subplots(1, len(violin_feats), figsize=(7 * len(violin_feats), 6))
if len(violin_feats) == 1: axes = [axes]

for ax_v, col in zip(axes, violin_feats):
    tmp = df[[col, "is_weekend"]].dropna()
    tmp["Weekend"] = tmp["is_weekend"].map({0: "Weekday", 1: "Weekend"})
    sns.violinplot(data=tmp, x="Weekend", y=col, ax=ax_v,
                   palette=["#3b82f6", "#f97316"], inner="box", cut=0)
    ax_v.set_title(f"{col} — Weekday vs Weekend", fontweight="bold", fontsize=11)
    ax_v.set_xlabel(""); ax_v.set_ylabel(col)

plt.suptitle("Violin Plots — Numeric Features by Weekday/Weekend",
             fontsize=14, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(f"{OUT}/11d_violin_plots.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 11d_violin_plots.png")

# ── 11e  EXTENDED CATEGORICAL DISTRIBUTIONS
print("       Building extended categorical plots …")
ext_cats = [
    ("junction_name",    12, "Top Junctions"),
    ("vehicle_type",     22, "Vehicle Types"),
    ("police_station",   15, "Top Police Stations"),
    ("validation_status", 5, "Validation Status"),
    ("month_name",       12, "Month"),
    ("day_part",          4, "Day Part"),
]
ext_cats = [(c, n, l) for c, n, l in ext_cats if c in df.columns]

nrows_ec = int(np.ceil(len(ext_cats) / 2))
fig, axes = plt.subplots(nrows_ec, 2, figsize=(20, 5 * nrows_ec))
axes = axes.flatten()
palette_ec = sns.color_palette("husl", 22)

for idx, (col, topn, title) in enumerate(ext_cats):
    ax_e = axes[idx]
    vc   = df[col].value_counts().head(topn)
    colors_bar = palette_ec[:len(vc)]
    ax_e.bar(range(len(vc)), vc.values, color=colors_bar, edgecolor="white", linewidth=0.6)
    ax_e.set_xticks(range(len(vc)))
    ax_e.set_xticklabels(vc.index, rotation=35, ha="right", fontsize=8)
    ax_e.set_title(title, fontweight="bold", fontsize=12)
    ax_e.set_ylabel("Count")
    for xi, vi in enumerate(vc.values):
        ax_e.text(xi, vi + vc.values.max() * 0.01, f"{vi:,}",
                  ha="center", fontsize=6.5, fontweight="bold", color="#333")

for j in range(len(ext_cats), len(axes)):
    axes[j].axis("off")

plt.suptitle("Extended Categorical Feature Distributions",
             fontsize=15, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/11e_categorical_extended.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 11e_categorical_extended.png")

# ── 11f  PAIRPLOT — key numeric features (sampled)
print("       Building pairplot …")
pair_cols = ["hour", "dist_from_center_km", "day_of_week", "month", "is_weekend"]
pair_cols  = [c for c in pair_cols if c in df.columns]
pair_sample = df[pair_cols + ["is_night"]].dropna().sample(min(8000, len(df)), random_state=42)

g = sns.pairplot(pair_sample, hue="is_night",
                 palette={0: "#3b82f6", 1: "#f97316"},
                 plot_kws=dict(alpha=0.3, s=8, edgecolor="none"),
                 diag_kind="kde",
                 corner=True)
g.figure.suptitle("Pairplot — Key Numeric Features (coloured by Night/Day)",
                   fontsize=13, fontweight="bold", y=1.02)
g.figure.set_size_inches(14, 12)
plt.savefig(f"{OUT}/11f_pairplot.png", dpi=120, bbox_inches="tight")
plt.close()
print("       Saved: 11f_pairplot.png")

# ── 11g  TIME-TO-VALIDATE distribution (log scale)
print("       Building time-to-validate distribution …")
ttv = df["time_to_validate_sec"].dropna()
ttv = ttv[(ttv > 0) & (ttv < ttv.quantile(0.99))]

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Raw
axes[0].hist(ttv, bins=80, color="#3b82f6", edgecolor="white", density=True, alpha=0.8)
axes[0].set_title("Time to Validate (raw, seconds)", fontweight="bold")
axes[0].set_xlabel("Seconds"); axes[0].set_ylabel("Density")
axes[0].axvline(ttv.mean(), color="#ef4444", linewidth=1.5, linestyle="--",
                label=f"Mean={ttv.mean()/3600:.1f}h")
axes[0].axvline(ttv.median(), color="#22c55e", linewidth=1.5, linestyle=":",
                label=f"Median={ttv.median()/3600:.1f}h")
axes[0].legend(fontsize=9)

# Log
log_ttv = np.log1p(ttv)
axes[1].hist(log_ttv, bins=80, color="#f97316", edgecolor="white", density=True, alpha=0.8)
axes[1].set_title("Time to Validate (log scale)", fontweight="bold")
axes[1].set_xlabel("log(1 + seconds)"); axes[1].set_ylabel("Density")
try:
    kde2 = stats.gaussian_kde(log_ttv.sample(min(20000, len(log_ttv)), random_state=1))
    xs2  = np.linspace(log_ttv.min(), log_ttv.max(), 300)
    axes[1].plot(xs2, kde2(xs2), color="#1e293b", linewidth=2)
except Exception: pass

plt.suptitle("Time-to-Validate Distribution", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/11g_time_to_validate.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 11g_time_to_validate.png")

# ─────────────────────────────────────────────────────────────────────────────
# SAVE ENGINEERED DATASET
# ─────────────────────────────────────────────────────────────────────────────
print("\n[SAVE] Writing engineered dataset …")
df.to_csv(f"{OUT}/engineered_dataset.csv", index=False)
print(f"       engineered_dataset.csv  →  {df.shape}")

elapsed = time.time() - t0
print("\n" + "=" * 60)
print(f"  ALL DONE in {elapsed:.1f}s  →  outputs/eda_report/")
print("=" * 60)

# Print index of all saved outputs
print("\n[OUTPUT INDEX]")
for f in sorted(os.listdir(OUT)):
    fp = os.path.join(OUT, f)
    size_kb = os.path.getsize(fp) / 1024
    print(f"  {f:<45}  {size_kb:>8.1f} KB")
