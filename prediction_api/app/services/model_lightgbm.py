"""
model_lightgbm.py — LightGBM Poisson regressor wrapper (§9 of spec).

WHY POISSON OBJECTIVE (not default L2/MSE):
  violation_count is sparse non-negative integer count data.  Poisson/
  Tweedie loss is the correct statistical choice because:
    1. It constrains predictions to be >= 0 (counts can't be negative).
    2. It penalises relative error, not absolute error — a miss of +1 on a
       location with true count=1 is treated as more significant than the
       same miss on a location with true count=10.
    3. It handles the extreme class imbalance (99.6% zero hours) better
       than MSE, which would be dominated by the mass of zeros.
  Default LGBMRegressor (L2) would heavily bias toward 0 and systematically
  under-predict the high-risk spots we most care about.

Model is saved via booster.save_model() (LightGBM native text format) and
reloaded via lgb.Booster(model_file=...) — no pickle dependency, format is
stable across minor LightGBM versions.

Retraining happens ONLY via scripts/train_models.py.  The FastAPI process
NEVER retrains — it only loads the saved artifact.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from app.config import LGBM_PARAMS, LGBM_MODEL, ALL_LGBM_FEATURES, FEATURE_NAMES

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Wrapper class
# ─────────────────────────────────────────────────────────────────

class LGBMPredictor:
    """
    Thin wrapper around a LightGBM Booster that handles:
    - train (with optional early-stopping on a validation set)
    - predict
    - save / load (native text format)
    """

    def __init__(self, lgbm_params: Optional[dict] = None) -> None:
        """
        Parameters
        ----------
        lgbm_params : optional dict of LightGBM training parameters.
            If None, falls back to LGBM_PARAMS from config (Poisson objective,
            Part 1 default).  Pass LGBM_SEVERITY_PARAMS for Part 2 training.
        """
        self._booster = None   # lgb.Booster, populated after train() or load()
        self._params  = lgbm_params if lgbm_params is not None else LGBM_PARAMS

    # ── Training ──────────────────────────────────────────────────

    def train(
        self,
        X_train: np.ndarray | pd.DataFrame,
        y_train: np.ndarray,
        X_val:   Optional[np.ndarray | pd.DataFrame] = None,
        y_val:   Optional[np.ndarray]                 = None,
        feature_names: Optional[list] = None,
        sample_weight: Optional[np.ndarray] = None,
    ) -> "LGBMPredictor":
        """
        Train on (X_train, y_train), optionally early-stopping on
        (X_val, y_val).

        Parameters
        ----------
        X_train, y_train : training features and labels
        X_val, y_val     : optional validation set for early stopping
        feature_names    : column names for SHAP / feature-importance display
        sample_weight    : optional per-sample weights (e.g. upweight non-zero severity rows)
        """
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ImportError("lightgbm is not installed. Run: pip install lightgbm") from exc

        params = dict(self._params)                   # don't mutate the config
        early_stop_rounds = params.pop("early_stopping_rounds", 30)

        fnames = feature_names or ALL_LGBM_FEATURES

        log.info(
            "Training LightGBM (objective=%s, n_estimators=%d, lr=%.3f) "
            "on %d samples, %d features",
            params["objective"], params["n_estimators"],
            params["learning_rate"], len(y_train), X_train.shape[1],
        )

        dtrain = lgb.Dataset(X_train, label=y_train, feature_name=fnames, weight=sample_weight)

        callbacks = [lgb.log_evaluation(period=50)]

        if X_val is not None and y_val is not None:
            dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
            callbacks.append(lgb.early_stopping(stopping_rounds=early_stop_rounds, verbose=True))
            valid_sets = [dval]
            valid_names = ["val"]
        else:
            valid_sets  = None
            valid_names = None

        self._booster = lgb.train(
            params         = params,
            train_set      = dtrain,
            valid_sets     = valid_sets,
            valid_names    = valid_names,
            callbacks      = callbacks,
        )

        best_iter = getattr(self._booster, "best_iteration", "N/A")
        log.info("LightGBM training complete. Best iteration: %s", best_iter)
        return self

    # ── Inference ─────────────────────────────────────────────────

    def predict(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        """
        Return predicted violation counts (non-negative floats).
        Poisson model outputs are the predicted Poisson rate — always >= 0.
        """
        if self._booster is None:
            raise RuntimeError("Model is not trained or loaded yet.")
        preds = self._booster.predict(X)
        # Clip at 0 as an extra safety net (Poisson should already ensure this)
        return np.clip(preds, 0, None).astype(np.float32)

    # ── Save / Load ───────────────────────────────────────────────

    def save(self, path: Path = LGBM_MODEL) -> None:
        """Persist using LightGBM's native text format (not pickle)."""
        if self._booster is None:
            raise RuntimeError("Nothing to save — model has not been trained.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._booster.save_model(str(path))
        log.info("LightGBM model saved -> %s", path)

    def load(self, path: Path = LGBM_MODEL) -> "LGBMPredictor":
        """Load a previously saved model without retraining."""
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ImportError("lightgbm is not installed.") from exc

        if not path.exists():
            raise FileNotFoundError(
                f"LightGBM model not found at {path}. "
                "Run scripts/train_models.py first."
            )
        self._booster = lgb.Booster(model_file=str(path))
        log.info("LightGBM model loaded from %s", path)
        return self

    @property
    def is_loaded(self) -> bool:
        return self._booster is not None

    def feature_importance(self) -> pd.DataFrame:
        """Return feature importances sorted descending (for debugging)."""
        if self._booster is None:
            return pd.DataFrame()
        names  = self._booster.feature_name()
        gains  = self._booster.feature_importance(importance_type="gain")
        splits = self._booster.feature_importance(importance_type="split")
        return (
            pd.DataFrame({"feature": names, "gain": gains, "split": splits})
            .sort_values("gain", ascending=False)
            .reset_index(drop=True)
        )


# ─────────────────────────────────────────────────────────────────
# Module-level singleton for FastAPI (loaded once at startup)
# ─────────────────────────────────────────────────────────────────

_predictor: Optional[LGBMPredictor] = None


def get_predictor() -> LGBMPredictor:
    """Return the module-level singleton, loading from disk if needed."""
    global _predictor
    if _predictor is None:
        _predictor = LGBMPredictor().load(LGBM_MODEL)
    return _predictor
