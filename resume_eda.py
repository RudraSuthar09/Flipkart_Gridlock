"""
Resume EDA from stage 10c onwards — SHAP 3D array fix + all distribution plots.
Already saved: 07c/d, 08, 09, 10a, 10b
"""

import os, warnings, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import shap
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")
OUT = "outputs/eda_report"
os.makedirs(OUT, exist_ok=True)
t0 = time.time()

# ─────────────────────────────────────────────────────────────────────────────
# 0. LOAD & REBUILD
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

df["hour"]                 = ref.dt.hour
df["day_of_week"]          = ref.dt.dayofweek
df["day_name"]             = ref.dt.day_name()
df["month"]                = ref.dt.month
df["month_name"]           = ref.dt.month_name()
df["is_weekend"]           = df["day_of_week"].isin([5, 6]).astype(int)
df["quarter"]              = ref.dt.quarter
df["time_to_validate_sec"] = (df["validation_dt"] - ref).dt.total_seconds()
df["is_night"]             = df["hour"].apply(lambda h: 1 if (h >= 21 or h <= 5) else 0)

def day_part(h):
    if   5 <= h < 12:  return "Morning"
    elif 12 <= h < 17: return "Afternoon"
    elif 17 <= h < 21: return "Evening"
    else:              return "Night"
df["day_part"] = df["hour"].apply(day_part)

B_LAT, B_LON = 12.9716, 77.5946
df["dist_from_center_km"] = np.sqrt(
    ((df["latitude"]  - B_LAT) * 111) ** 2 +
    ((df["longitude"] - B_LON) * 111 * np.cos(np.radians(B_LAT))) ** 2
)
thr = df["dist_from_center_km"].quantile(0.90)
df["is_periphery"] = (df["dist_from_center_km"] > thr).astype(int)
print(f"       Features rebuilt. ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# RE-TRAIN RF
# ─────────────────────────────────────────────────────────────────────────────
print("\n[RF] Re-training Random Forest for SHAP …")
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
X = feat_df[feature_cols]; y = feat_df["target"]

importances = (pd.read_csv(f"{OUT}/09_feature_importance.csv", index_col=0)
                 .squeeze("columns")
                 .sort_values(ascending=False))
top3 = importances.head(3).index.tolist()
print(f"       Top 3 features: {top3}")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)
rf = RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=-1,
                             random_state=42, class_weight="balanced")
rf.fit(X_train, y_train)
print(f"       RF trained. ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 10c  SHAP — fixed for both old-API (list) and new-API (3-D ndarray)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[10c] SHAP dependence plots …")
SHAP_SAMPLE = min(3000, len(X_test))
X_shap = X_test.sample(SHAP_SAMPLE, random_state=42)

explainer   = shap.TreeExplainer(rf)
shap_values = explainer.shap_values(X_shap)

# ── Robust sv extraction ──────────────────────────────────────────────────────
if isinstance(shap_values, list):
    # Old SHAP API: list of arrays, one per class
    sv = shap_values[1]                          # shape (n, features)
elif isinstance(shap_values, np.ndarray):
    if shap_values.ndim == 3:
        # New SHAP API: single 3-D array (n, features, classes)
        sv = shap_values[:, :, 1]               # shape (n, features)
    else:
        sv = shap_values                         # already 2-D
else:
    # shap.Explanation object (newer still)
    sv = np.array(shap_values.values)
    if sv.ndim == 3:
        sv = sv[:, :, 1]

print(f"       sv shape: {sv.shape}")

# Save SHAP importance CSV
shap_means = pd.Series(
    np.abs(sv).mean(axis=0), index=feature_cols
).sort_values(ascending=False)
shap_means.to_csv(f"{OUT}/10_shap_importance.csv")
print("       Saved: 10_shap_importance.csv")

# Dependence plots with interaction_index=None to avoid numpy concat bug
fig, axes_dep = plt.subplots(1, 3, figsize=(19, 5))
for ax_d, feat in zip(axes_dep, top3):
    feat_idx = feature_cols.index(feat)
    try:
        shap.dependence_plot(feat, sv, X_shap,
                             feature_names=feature_cols,
                             interaction_index=None,
                             ax=ax_d, show=False)
    except Exception as e:
        print(f"       [WARN] dependence_plot fallback for {feat}: {e}")
        ax_d.scatter(X_shap[feat].values, sv[:, feat_idx],
                     alpha=0.3, s=6, c="#3b82f6", edgecolors="none")
        ax_d.set_xlabel(feat, fontsize=9)
        ax_d.set_ylabel(f"SHAP value for\n{feat}", fontsize=9)
    ax_d.set_title(f"SHAP Dependence: {feat}", fontweight="bold", fontsize=10)

plt.tight_layout()
plt.savefig(f"{OUT}/10c_shap_dependence.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 10c_shap_dependence.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11a  NUMERIC DISTRIBUTIONS — Histogram + KDE  (dark theme)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11a] Numeric distributions …")

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
BG_DARK  = "#0f172a"
BG_PANEL = "#1e293b"

fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 5 * nrows),
                         facecolor=BG_DARK)
axes = axes.flatten()
cmap_list = plt.cm.tab10(np.linspace(0, 0.9, n_num))

for idx, (col, label) in enumerate(numeric_feats.items()):
    ax = axes[idx]
    ax.set_facecolor(BG_PANEL)
    if col not in df.columns:
        ax.axis("off"); continue

    series = df[col].dropna()
    color  = cmap_list[idx]

    if col == "time_to_validate_sec":
        series = series[(series >= 0) & (series < series.quantile(0.99))]

    n_bins = min(60, max(10, series.nunique()))
    ax.hist(series, bins=n_bins, color=color, edgecolor="none",
            alpha=0.75, density=True)

    try:
        samp = series.sample(min(20000, len(series)), random_state=42)
        kde  = stats.gaussian_kde(samp)
        xs   = np.linspace(series.min(), series.max(), 300)
        ax.plot(xs, kde(xs), color="white",  linewidth=2.2, zorder=3)
        ax.plot(xs, kde(xs), color=color,    linewidth=1.2,
                linestyle="--", zorder=4, alpha=0.7)
    except Exception:
        pass

    ax.axvline(series.mean(),   color="#ef4444", linewidth=1.5,
               linestyle="--", label=f"Mean={series.mean():.2f}")
    ax.axvline(series.median(), color="#22c55e", linewidth=1.5,
               linestyle=":",  label=f"Median={series.median():.2f}")

    sk = series.skew(); ku = series.kurtosis()
    ax.set_title(label, fontweight="bold", fontsize=11, color="white", pad=6)
    ax.set_xlabel(label, fontsize=9, color="#94a3b8")
    ax.set_ylabel("Density", fontsize=9, color="#94a3b8")
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for spine in ax.spines.values(): spine.set_edgecolor("#334155")
    ax.legend(fontsize=7, loc="upper right",
              facecolor=BG_PANEL, edgecolor="#334155", labelcolor="white")
    ax.text(0.02, 0.97,
            f"n={len(series):,}\nSkew={sk:.2f}\nKurt={ku:.2f}\nStd={series.std():.2f}",
            transform=ax.transAxes, fontsize=7.5, va="top", color="white",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_DARK, alpha=0.8))

for j in range(n_num, len(axes)):
    axes[j].set_facecolor(BG_DARK); axes[j].axis("off")

fig.suptitle("Numeric Feature Distributions — Histogram + KDE",
             fontsize=16, fontweight="bold", color="white", y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/11a_numeric_distributions.png", dpi=150,
            bbox_inches="tight", facecolor=BG_DARK)
plt.close()
plt.rcParams.update(plt.rcParamsDefault)
print(f"       Saved: 11a_numeric_distributions.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11b  BINARY FLAG DONUTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11b] Binary flag donut charts …")
flag_feats = {
    "is_weekend"  : ["Weekday", "Weekend"],
    "is_night"    : ["Daytime", "Night"],
    "is_periphery": ["Central", "Periphery"],
}
donut_colors = [["#3b82f6","#f97316"], ["#8b5cf6","#f59e0b"], ["#10b981","#ef4444"]]

fig, axes_b = plt.subplots(1, 3, figsize=(18, 6))
for idx, (col, labels) in enumerate(flag_feats.items()):
    ax = axes_b[idx]
    if col not in df.columns: ax.axis("off"); continue
    counts = df[col].value_counts().sort_index()
    _, _, autotexts = ax.pie(
        counts, labels=labels, autopct="%1.1f%%",
        colors=donut_colors[idx], startangle=90,
        wedgeprops=dict(width=0.52, edgecolor="white", linewidth=2.5),
        textprops=dict(fontsize=12, fontweight="bold"))
    for at in autotexts: at.set_fontsize(11); at.set_fontweight("bold")
    ax.set_title(col, fontweight="bold", fontsize=14, pad=12)
    ax.text(0, 0, f"n={len(df):,}", ha="center", va="center",
            fontsize=10, fontweight="bold", color="#555")

plt.suptitle("Binary / Flag Feature Distributions",
             fontsize=15, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(f"{OUT}/11b_binary_features.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 11b_binary_features.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11c  HOURLY HEATMAP
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11c] Hour × Day-of-Week heatmap …")
pivot = (df.groupby(["day_of_week", "hour"])
           .size()
           .reset_index(name="count")
           .pivot(index="day_of_week", columns="hour", values="count")
           .fillna(0))
day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

fig, ax = plt.subplots(figsize=(18, 5))
sns.heatmap(pivot, cmap="YlOrRd", ax=ax, linewidths=0.4,
            yticklabels=day_labels, annot=True, fmt=".0f",
            annot_kws={"size": 7},
            cbar_kws={"label": "Violation Count", "shrink": 0.8})
ax.set_title("Violation Intensity — Hour of Day × Day of Week",
             fontweight="bold", fontsize=13, pad=12)
ax.set_xlabel("Hour of Day", fontsize=11)
ax.set_ylabel("Day of Week", fontsize=11)
plt.tight_layout()
plt.savefig(f"{OUT}/11c_hourly_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 11c_hourly_heatmap.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11d  VIOLIN PLOTS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11d] Violin plots …")
violin_feats = ["hour", "dist_from_center_km", "month"]
violin_feats = [c for c in violin_feats if c in df.columns]

fig, axes_v = plt.subplots(1, len(violin_feats), figsize=(7 * len(violin_feats), 6))
if len(violin_feats) == 1: axes_v = [axes_v]

for ax_v, col in zip(axes_v, violin_feats):
    tmp = df[[col, "is_weekend"]].dropna().copy()
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
print(f"       Saved: 11d_violin_plots.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11e  EXTENDED CATEGORICAL DISTRIBUTIONS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11e] Extended categorical distributions …")
ext_cats = [
    ("junction_name",     12, "Top 12 Junctions"),
    ("vehicle_type",      22, "Vehicle Types"),
    ("police_station",    15, "Top 15 Police Stations"),
    ("validation_status",  5, "Validation Status"),
    ("month_name",        12, "Month"),
    ("day_part",           4, "Day Part"),
]
ext_cats = [(c, n, l) for c, n, l in ext_cats if c in df.columns]
nrows_ec = int(np.ceil(len(ext_cats) / 2))
palette_ec = sns.color_palette("husl", 22)

fig, axes_ec = plt.subplots(nrows_ec, 2, figsize=(20, 5 * nrows_ec))
axes_ec = axes_ec.flatten()

for idx, (col, topn, title) in enumerate(ext_cats):
    ax_e = axes_ec[idx]
    vc   = df[col].value_counts().head(topn)
    ax_e.bar(range(len(vc)), vc.values, color=palette_ec[:len(vc)],
             edgecolor="white", linewidth=0.6)
    ax_e.set_xticks(range(len(vc)))
    ax_e.set_xticklabels(vc.index, rotation=35, ha="right", fontsize=8)
    ax_e.set_title(title, fontweight="bold", fontsize=12)
    ax_e.set_ylabel("Count")
    for xi, vi in enumerate(vc.values):
        ax_e.text(xi, vi + vc.values.max() * 0.01, f"{vi:,}",
                  ha="center", fontsize=6.5, fontweight="bold", color="#333")

for j in range(len(ext_cats), len(axes_ec)):
    axes_ec[j].axis("off")

plt.suptitle("Extended Categorical Feature Distributions",
             fontsize=15, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig(f"{OUT}/11e_categorical_extended.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 11e_categorical_extended.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11f  PAIRPLOT
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11f] Pairplot …")
pair_cols = ["hour", "dist_from_center_km", "day_of_week", "month", "is_weekend"]
pair_cols = [c for c in pair_cols if c in df.columns]
pair_sample = (df[pair_cols + ["is_night"]]
               .dropna()
               .sample(min(8000, len(df)), random_state=42))

g = sns.pairplot(pair_sample, hue="is_night",
                 palette={0: "#3b82f6", 1: "#f97316"},
                 plot_kws=dict(alpha=0.3, s=8, edgecolor="none"),
                 diag_kind="kde", corner=True)
g.figure.suptitle("Pairplot — Key Numeric Features (Blue=Day, Orange=Night)",
                   fontsize=13, fontweight="bold", y=1.02)
g.figure.set_size_inches(14, 12)
plt.savefig(f"{OUT}/11f_pairplot.png", dpi=120, bbox_inches="tight")
plt.close()
print(f"       Saved: 11f_pairplot.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# 11g  TIME-TO-VALIDATE
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11g] Time-to-validate distribution …")
ttv = df["time_to_validate_sec"].dropna()
ttv = ttv[(ttv > 0) & (ttv < ttv.quantile(0.99))]

fig, axes_t = plt.subplots(1, 2, figsize=(14, 5))

axes_t[0].hist(ttv, bins=80, color="#3b82f6", edgecolor="white", density=True, alpha=0.8)
axes_t[0].set_title("Time to Validate (raw)", fontweight="bold")
axes_t[0].set_xlabel("Seconds"); axes_t[0].set_ylabel("Density")
axes_t[0].axvline(ttv.mean(),   color="#ef4444", lw=1.8, ls="--",
                  label=f"Mean = {ttv.mean()/3600:.1f} h")
axes_t[0].axvline(ttv.median(), color="#22c55e", lw=1.8, ls=":",
                  label=f"Median = {ttv.median()/3600:.1f} h")
axes_t[0].legend(fontsize=9)

log_ttv = np.log1p(ttv)
axes_t[1].hist(log_ttv, bins=80, color="#f97316", edgecolor="white", density=True, alpha=0.8)
axes_t[1].set_title("Time to Validate (log scale)", fontweight="bold")
axes_t[1].set_xlabel("log(1 + seconds)"); axes_t[1].set_ylabel("Density")
try:
    kde2 = stats.gaussian_kde(log_ttv.sample(min(20000, len(log_ttv)), random_state=1))
    xs2  = np.linspace(log_ttv.min(), log_ttv.max(), 300)
    axes_t[1].plot(xs2, kde2(xs2), color="#1e293b", linewidth=2.2)
except Exception: pass

plt.suptitle("Time-to-Validate Distribution", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/11g_time_to_validate.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"       Saved: 11g_time_to_validate.png  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# SAVE ENGINEERED DATASET
# ─────────────────────────────────────────────────────────────────────────────
print("\n[SAVE] Writing engineered_dataset.csv …")
df.to_csv(f"{OUT}/engineered_dataset.csv", index=False)
print(f"       Shape: {df.shape}")

# FINAL INDEX
elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"  ALL DONE in {elapsed:.1f}s")
print(f"{'='*60}\n[OUTPUT INDEX]")
for f in sorted(os.listdir(OUT)):
    fp  = os.path.join(OUT, f)
    tag = "PNG" if f.endswith(".png") else "CSV"
    print(f"  [{tag}]  {f:<52}  {os.path.getsize(fp)/1024:>8.1f} KB")
