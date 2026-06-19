"""
Resume from stage 7b (Cramer's V) — all prior outputs already saved.
Runs: Cramer's V, categorical plots, RF feature importance, SHAP.
"""
import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

# ── Reload & rebuild engineered features ─────────────────────────────────────
print("[INFO] Loading dataset ...")
df = pd.read_csv("dataset.csv", low_memory=False)
print(f"       shape: {df.shape}")

# Rebuild temporal features
def safe_parse(col):
    return pd.to_datetime(df[col], utc=True, errors="coerce")

df["created_dt"]    = safe_parse("created_datetime")
df["validation_dt"] = safe_parse("validation_timestamp")
ref = df["created_dt"]

df["hour"]         = ref.dt.hour
df["day_of_week"]  = ref.dt.dayofweek
df["day_name"]     = ref.dt.day_name()
df["month"]        = ref.dt.month
df["month_name"]   = ref.dt.month_name()
df["is_weekend"]   = df["day_of_week"].isin([5, 6]).astype(int)
df["is_night"]     = df["hour"].apply(lambda h: 1 if (h >= 21 or h <= 5) else 0)
df["quarter"]      = ref.dt.quarter
df["time_to_validate_sec"] = (df["validation_dt"] - ref).dt.total_seconds()

def day_part(h):
    if 5 <= h < 12:    return "Morning"
    elif 12 <= h < 17: return "Afternoon"
    elif 17 <= h < 21: return "Evening"
    else:              return "Night"
df["day_part"] = df["hour"].apply(day_part)

# Rebuild geo features
B_LAT, B_LON = 12.9716, 77.5946
df["dist_from_center_km"] = np.sqrt(
    ((df["latitude"]  - B_LAT) * 111)**2 +
    ((df["longitude"] - B_LON) * 111 * np.cos(np.radians(B_LAT)))**2
)
threshold = df["dist_from_center_km"].quantile(0.90)
df["is_periphery"] = (df["dist_from_center_km"] > threshold).astype(int)
print("       Features rebuilt.")

# ── 7b. CRAMER'S V ────────────────────────────────────────────────────────────
print("\n[7b] Cramer's V ...")

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
print(cramer_data.to_string())

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(cramer_data.astype(float), annot=True, fmt=".2f", cmap="YlOrRd",
            ax=ax, linewidths=0.5, vmin=0, vmax=1, square=True,
            annot_kws={"size": 9})
ax.set_title("Cramer's V - Categorical Associations", fontweight="bold", fontsize=13)
plt.tight_layout()
plt.savefig(f"{OUT}/07d_cramers_v_heatmap.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 07d_cramers_v_heatmap.png")

# ── 8. CATEGORICAL DISTRIBUTIONS ─────────────────────────────────────────────
print("\n[8] Categorical distributions ...")
top_cats = ["violation_type","vehicle_type","police_station",
            "validation_status","day_part","day_name"]
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

# ── 9. FEATURE IMPORTANCE ─────────────────────────────────────────────────────
print("\n[9] Random Forest feature importance ...")

df["target"] = (df["validation_status"] == "approved").astype(int)

feature_cols = [
    "latitude","longitude","dist_from_center_km","is_periphery",
    "hour","day_of_week","month","is_weekend","is_night","quarter",
    "center_code",
]
le = LabelEncoder()
for c in ["violation_type","vehicle_type","police_station","day_part"]:
    if c in df.columns:
        df[c + "_enc"] = le.fit_transform(df[c].astype(str))
        feature_cols.append(c + "_enc")

feat_df = df[feature_cols + ["target"]].dropna()
X = feat_df[feature_cols]
y = feat_df["target"]
print(f"       Dataset: {X.shape}  |  target balance:\n{y.value_counts()}")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

rf = RandomForestClassifier(n_estimators=200, max_depth=10, n_jobs=-1,
                            random_state=42, class_weight="balanced")
rf.fit(X_train, y_train)
print("\n-- Classification Report --")
print(classification_report(y_test, rf.predict(X_test)))

importances = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
importances.to_csv(f"{OUT}/09_feature_importance.csv")
print("\n-- Feature Importances --")
print(importances.to_string())

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

# ── 10. SHAP ──────────────────────────────────────────────────────────────────
print("\n[10] SHAP analysis ...")

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

# Dependence plots for top 3 features
top3 = importances.head(3).index.tolist()
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, feat in zip(axes, top3):
    shap.dependence_plot(feat, sv, X_shap, feature_names=feature_cols, ax=ax, show=False)
    ax.set_title(f"SHAP Dependence: {feat}", fontweight="bold", fontsize=10)
plt.tight_layout()
plt.savefig(f"{OUT}/10c_shap_dependence.png", dpi=150, bbox_inches="tight")
plt.close()
print("       Saved: 10c_shap_dependence.png")

# SHAP mean magnitudes CSV
shap_means = pd.Series(np.abs(sv).mean(axis=0), index=feature_cols).sort_values(ascending=False)
shap_means.to_csv(f"{OUT}/10_shap_importance.csv")
print("\n-- SHAP Mean |values| --")
print(shap_means.to_string())

# ── SAVE ENGINEERED DATASET ───────────────────────────────────────────────────
print("\n[DONE] Saving engineered dataset ...")
df.to_csv(f"{OUT}/engineered_dataset.csv", index=False)
print(f"       engineered_dataset.csv -> {df.shape}")

print("\n" + "="*60)
print("  ALL DONE. Check outputs/eda_report/ for all results.")
print("="*60)
