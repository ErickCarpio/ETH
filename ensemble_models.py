"""
Ensemble Models - Phase 6
Multiple base models with optimized hyperparameters for regime classification

Models included:
1. XGBoost - Gradient boosting with regularization
2. LightGBM - Fast gradient boosting with leaf-wise growth
3. CatBoost - Gradient boosting optimized for categorical features
4. Random Forest - Ensemble of decision trees
"""

import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier, Pool
from sklearn.ensemble import RandomForestClassifier
import optuna
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import f1_score, accuracy_score
from sklearn.utils.class_weight import compute_class_weight
from typing import Dict, Optional, Tuple
import logging
from pathlib import Path
import joblib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseRegimeModel:
    """Base class for all regime classification models"""

    def __init__(self, n_classes: int = 4, model_dir: str = "./models"):
        self.n_classes = n_classes
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True, parents=True)

        self.model = None
        self.best_params = None
        self.feature_importance = None
        self.model_name = "base"

    def _calculate_balanced_weights(self, y_train, temporal_weights):
        """Combine temporal weights with class weights"""
        classes = np.unique(y_train)
        class_weights = compute_class_weight(
            class_weight='balanced',
            classes=classes,
            y=y_train
        )
        class_weight_dict = dict(zip(classes, class_weights))
        sample_class_weights = np.array([class_weight_dict[y] for y in y_train])
        final_weights = temporal_weights * sample_class_weights
        return final_weights

    def predict(self, X):
        """Predict class labels"""
        return self.model.predict(X)

    def predict_proba(self, X):
        """Predict class probabilities"""
        return self.model.predict_proba(X)

    def save_model(self, model_name: str = None):
        """Save model to disk"""
        raise NotImplementedError

    def load_model(self, model_name: str = None):
        """Load model from disk"""
        raise NotImplementedError


class XGBoostModel(BaseRegimeModel):
    """XGBoost model with Optuna optimization"""

    def __init__(self, n_classes: int = 4, optuna_trials: int = 50, model_dir: str = "./models"):
        super().__init__(n_classes, model_dir)
        self.optuna_trials = optuna_trials
        self.model_name = "xgboost"

    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        """Optimize XGBoost hyperparameters using Optuna"""
        logger.info(f"[XGBoost] Optimizing ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)

        def objective(trial):
            params = {
                'objective': 'multi:softmax',
                'num_class': self.n_classes,
                'eval_metric': 'mlogloss',
                'tree_method': 'hist',
                'device': 'cpu',
                'max_depth': trial.suggest_int('max_depth', 3, 12),
                'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.3, log=True),
                'n_estimators': trial.suggest_int('n_estimators', 100, 800),
                'min_child_weight': trial.suggest_int('min_child_weight', 1, 20),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'gamma': trial.suggest_float('gamma', 0, 10),
                'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 20.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 20.0, log=True),
            }

            tscv = TimeSeriesSplit(n_splits=n_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X_train):
                X_f_train = X_train.iloc[train_idx]
                y_f_train = y_train.iloc[train_idx]
                w_f_train = balanced_weights[train_idx]
                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]

                model = xgb.XGBClassifier(**params, random_state=42)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train, verbose=False)

                y_pred = model.predict(X_f_val)
                score = f1_score(y_f_val, y_pred, average='weighted')
                scores.append(score)

            return np.mean(scores)

        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=self.optuna_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.best_params.update({
            'objective': 'multi:softmax',
            'num_class': self.n_classes,
            'eval_metric': 'mlogloss',
            'tree_method': 'hist',
            'device': 'cpu',
            'random_state': 42
        })

        logger.info(f"[XGBoost] Best F1: {study.best_value:.4f}")
        return self.best_params

    def train(self, X_train, y_train, sample_weights, X_val=None, y_val=None, optimize=True):
        """Train XGBoost model"""
        logger.info("=" * 60)
        logger.info("[XGBoost] TRAINING")
        logger.info("=" * 60)

        final_weights = self._calculate_balanced_weights(y_train, sample_weights)

        if optimize or self.best_params is None:
            self.optimize_hyperparameters(X_train, y_train, sample_weights)

        self.model = xgb.XGBClassifier(**self.best_params)

        eval_set = [(X_train, y_train)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))

        self.model.fit(
            X_train, y_train,
            sample_weight=final_weights,
            eval_set=eval_set,
            verbose=False
        )

        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        logger.info(f"[XGBoost] Top 5 Features:\n{self.feature_importance.head(5).to_string(index=False)}")

        if X_val is not None and y_val is not None:
            y_val_pred = self.predict(X_val)
            accuracy = accuracy_score(y_val, y_val_pred)
            f1 = f1_score(y_val, y_val_pred, average='weighted')
            logger.info(f"[XGBoost] Validation Accuracy: {accuracy:.4f}, F1: {f1:.4f}")

        return self.model

    def save_model(self, model_name: str = "xgboost_regime.json"):
        """Save XGBoost model"""
        if self.model is None:
            return
        model_path = self.model_dir / model_name
        self.model.save_model(model_path)

        metadata = {
            'best_params': self.best_params,
            'feature_importance': self.feature_importance.to_dict() if self.feature_importance is not None else None,
            'n_classes': self.n_classes
        }
        joblib.dump(metadata, self.model_dir / f"{model_name.replace('.json', '_metadata.pkl')}")
        logger.info(f"[XGBoost] Model saved: {model_path}")

    def load_model(self, model_name: str = "xgboost_regime.json"):
        """Load XGBoost model"""
        model_path = self.model_dir / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        self.model = xgb.XGBClassifier()
        self.model.load_model(model_path)

        metadata_path = self.model_dir / f"{model_name.replace('.json', '_metadata.pkl')}"
        if metadata_path.exists():
            metadata = joblib.load(metadata_path)
            self.best_params = metadata['best_params']
            self.feature_importance = pd.DataFrame(metadata['feature_importance']) if metadata['feature_importance'] else None
            self.n_classes = metadata['n_classes']
        logger.info(f"[XGBoost] Model loaded: {model_path}")


class LightGBMModel(BaseRegimeModel):
    """LightGBM model with Optuna optimization"""

    def __init__(self, n_classes: int = 4, optuna_trials: int = 50, model_dir: str = "./models"):
        super().__init__(n_classes, model_dir)
        self.optuna_trials = optuna_trials
        self.model_name = "lightgbm"

    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        """Optimize LightGBM hyperparameters using Optuna"""
        logger.info(f"[LightGBM] Optimizing ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)

        def objective(trial):
            params = {
                'objective': 'multiclass',
                'num_class': self.n_classes,
                'metric': 'multi_logloss',
                'boosting_type': 'gbdt',
                'num_leaves': trial.suggest_int('num_leaves', 20, 150),
                'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.3, log=True),
                'n_estimators': trial.suggest_int('n_estimators', 100, 800),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
                'min_split_gain': trial.suggest_float('min_split_gain', 0, 15),
                'verbose': -1
            }

            tscv = TimeSeriesSplit(n_splits=n_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X_train):
                X_f_train = X_train.iloc[train_idx]
                y_f_train = y_train.iloc[train_idx]
                w_f_train = balanced_weights[train_idx]
                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]

                model = lgb.LGBMClassifier(**params, random_state=42)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train)

                y_pred = model.predict(X_f_val)
                score = f1_score(y_f_val, y_pred, average='weighted')
                scores.append(score)

            return np.mean(scores)

        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=43))
        study.optimize(objective, n_trials=self.optuna_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.best_params.update({
            'objective': 'multiclass',
            'num_class': self.n_classes,
            'metric': 'multi_logloss',
            'boosting_type': 'gbdt',
            'random_state': 42,
            'verbose': -1
        })

        logger.info(f"[LightGBM] Best F1: {study.best_value:.4f}")
        return self.best_params

    def train(self, X_train, y_train, sample_weights, X_val=None, y_val=None, optimize=True):
        """Train LightGBM model"""
        logger.info("=" * 60)
        logger.info("[LightGBM] TRAINING")
        logger.info("=" * 60)

        final_weights = self._calculate_balanced_weights(y_train, sample_weights)

        if optimize or self.best_params is None:
            self.optimize_hyperparameters(X_train, y_train, sample_weights)

        self.model = lgb.LGBMClassifier(**self.best_params)

        self.model.fit(
            X_train, y_train,
            sample_weight=final_weights
        )

        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        logger.info(f"[LightGBM] Top 5 Features:\n{self.feature_importance.head(5).to_string(index=False)}")

        if X_val is not None and y_val is not None:
            y_val_pred = self.predict(X_val)
            accuracy = accuracy_score(y_val, y_val_pred)
            f1 = f1_score(y_val, y_val_pred, average='weighted')
            logger.info(f"[LightGBM] Validation Accuracy: {accuracy:.4f}, F1: {f1:.4f}")

        return self.model

    def save_model(self, model_name: str = "lightgbm_regime.txt"):
        """Save LightGBM model"""
        if self.model is None:
            return
        model_path = self.model_dir / model_name
        joblib.dump(self.model, model_path)

        metadata = {
            'best_params': self.best_params,
            'feature_importance': self.feature_importance.to_dict() if self.feature_importance is not None else None,
            'n_classes': self.n_classes
        }
        joblib.dump(metadata, self.model_dir / f"{model_name.replace('.txt', '_metadata.pkl')}")
        logger.info(f"[LightGBM] Model saved: {model_path}")

    def load_model(self, model_name: str = "lightgbm_regime.txt"):
        """Load LightGBM model"""
        model_path = self.model_dir / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        self.model = joblib.load(model_path)

        metadata_path = self.model_dir / f"{model_name.replace('.txt', '_metadata.pkl')}"
        if metadata_path.exists():
            metadata = joblib.load(metadata_path)
            self.best_params = metadata['best_params']
            self.feature_importance = pd.DataFrame(metadata['feature_importance']) if metadata['feature_importance'] else None
            self.n_classes = metadata['n_classes']
        logger.info(f"[LightGBM] Model loaded: {model_path}")


class CatBoostModel(BaseRegimeModel):
    """CatBoost model with Optuna optimization"""

    def __init__(self, n_classes: int = 4, optuna_trials: int = 50, model_dir: str = "./models"):
        super().__init__(n_classes, model_dir)
        self.optuna_trials = optuna_trials
        self.model_name = "catboost"

    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        """Optimize CatBoost hyperparameters using Optuna"""
        logger.info(f"[CatBoost] Optimizing ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)

        def objective(trial):
            params = {
                'iterations': trial.suggest_int('iterations', 100, 1000),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'depth': trial.suggest_int('depth', 4, 10),
                'l2_leaf_reg': trial.suggest_float('l2_leaf_reg', 1, 10),
                'border_count': trial.suggest_int('border_count', 32, 255),
                'bagging_temperature': trial.suggest_float('bagging_temperature', 0, 1),
                'random_strength': trial.suggest_float('random_strength', 0, 10),
                'loss_function': 'MultiClass',
                'eval_metric': 'TotalF1:average=Weighted',
                'random_seed': 42,
                'verbose': False
            }

            tscv = TimeSeriesSplit(n_splits=n_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X_train):
                X_f_train = X_train.iloc[train_idx]
                y_f_train = y_train.iloc[train_idx]
                w_f_train = balanced_weights[train_idx]
                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]

                model = CatBoostClassifier(**params)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train, verbose=False)

                y_pred = model.predict(X_f_val)
                score = f1_score(y_f_val, y_pred, average='weighted')
                scores.append(score)

            return np.mean(scores)

        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=44))
        study.optimize(objective, n_trials=self.optuna_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.best_params.update({
            'loss_function': 'MultiClass',
            'eval_metric': 'TotalF1:average=Weighted',
            'random_seed': 42,
            'verbose': False
        })

        logger.info(f"[CatBoost] Best F1: {study.best_value:.4f}")
        return self.best_params

    def train(self, X_train, y_train, sample_weights, X_val=None, y_val=None, optimize=True):
        """Train CatBoost model"""
        logger.info("=" * 60)
        logger.info("[CatBoost] TRAINING")
        logger.info("=" * 60)

        final_weights = self._calculate_balanced_weights(y_train, sample_weights)

        if optimize or self.best_params is None:
            self.optimize_hyperparameters(X_train, y_train, sample_weights)

        self.model = CatBoostClassifier(**self.best_params)

        self.model.fit(
            X_train, y_train,
            sample_weight=final_weights,
            verbose=False
        )

        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        logger.info(f"[CatBoost] Top 5 Features:\n{self.feature_importance.head(5).to_string(index=False)}")

        if X_val is not None and y_val is not None:
            y_val_pred = self.predict(X_val)
            accuracy = accuracy_score(y_val, y_val_pred)
            f1 = f1_score(y_val, y_val_pred, average='weighted')
            logger.info(f"[CatBoost] Validation Accuracy: {accuracy:.4f}, F1: {f1:.4f}")

        return self.model

    def save_model(self, model_name: str = "catboost_regime.cbm"):
        """Save CatBoost model"""
        if self.model is None:
            return
        model_path = self.model_dir / model_name
        self.model.save_model(str(model_path))

        metadata = {
            'best_params': self.best_params,
            'feature_importance': self.feature_importance.to_dict() if self.feature_importance is not None else None,
            'n_classes': self.n_classes
        }
        joblib.dump(metadata, self.model_dir / f"{model_name.replace('.cbm', '_metadata.pkl')}")
        logger.info(f"[CatBoost] Model saved: {model_path}")

    def load_model(self, model_name: str = "catboost_regime.cbm"):
        """Load CatBoost model"""
        model_path = self.model_dir / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        self.model = CatBoostClassifier()
        self.model.load_model(str(model_path))

        metadata_path = self.model_dir / f"{model_name.replace('.cbm', '_metadata.pkl')}"
        if metadata_path.exists():
            metadata = joblib.load(metadata_path)
            self.best_params = metadata['best_params']
            self.feature_importance = pd.DataFrame(metadata['feature_importance']) if metadata['feature_importance'] else None
            self.n_classes = metadata['n_classes']
        logger.info(f"[CatBoost] Model loaded: {model_path}")


class RandomForestModel(BaseRegimeModel):
    """Random Forest model with Optuna optimization"""

    def __init__(self, n_classes: int = 4, optuna_trials: int = 50, model_dir: str = "./models"):
        super().__init__(n_classes, model_dir)
        self.optuna_trials = optuna_trials
        self.model_name = "random_forest"

    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        """Optimize Random Forest hyperparameters using Optuna"""
        logger.info(f"[RandomForest] Optimizing ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)

        def objective(trial):
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 100, 500),
                'max_depth': trial.suggest_int('max_depth', 5, 30),
                'min_samples_split': trial.suggest_int('min_samples_split', 2, 20),
                'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 10),
                'max_features': trial.suggest_categorical('max_features', ['sqrt', 'log2', None]),
                'bootstrap': True,
                'random_state': 42,
                'n_jobs': -1
            }

            tscv = TimeSeriesSplit(n_splits=n_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X_train):
                X_f_train = X_train.iloc[train_idx]
                y_f_train = y_train.iloc[train_idx]
                w_f_train = balanced_weights[train_idx]
                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]

                model = RandomForestClassifier(**params)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train)

                y_pred = model.predict(X_f_val)
                score = f1_score(y_f_val, y_pred, average='weighted')
                scores.append(score)

            return np.mean(scores)

        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=45))
        study.optimize(objective, n_trials=self.optuna_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.best_params.update({
            'bootstrap': True,
            'random_state': 42,
            'n_jobs': -1
        })

        logger.info(f"[RandomForest] Best F1: {study.best_value:.4f}")
        return self.best_params

    def train(self, X_train, y_train, sample_weights, X_val=None, y_val=None, optimize=True):
        """Train Random Forest model"""
        logger.info("=" * 60)
        logger.info("[RandomForest] TRAINING")
        logger.info("=" * 60)

        final_weights = self._calculate_balanced_weights(y_train, sample_weights)

        if optimize or self.best_params is None:
            self.optimize_hyperparameters(X_train, y_train, sample_weights)

        self.model = RandomForestClassifier(**self.best_params)

        self.model.fit(
            X_train, y_train,
            sample_weight=final_weights
        )

        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        logger.info(f"[RandomForest] Top 5 Features:\n{self.feature_importance.head(5).to_string(index=False)}")

        if X_val is not None and y_val is not None:
            y_val_pred = self.predict(X_val)
            accuracy = accuracy_score(y_val, y_val_pred)
            f1 = f1_score(y_val, y_val_pred, average='weighted')
            logger.info(f"[RandomForest] Validation Accuracy: {accuracy:.4f}, F1: {f1:.4f}")

        return self.model

    def save_model(self, model_name: str = "random_forest_regime.pkl"):
        """Save Random Forest model"""
        if self.model is None:
            return
        model_path = self.model_dir / model_name
        joblib.dump(self.model, model_path)

        metadata = {
            'best_params': self.best_params,
            'feature_importance': self.feature_importance.to_dict() if self.feature_importance is not None else None,
            'n_classes': self.n_classes
        }
        joblib.dump(metadata, self.model_dir / f"{model_name.replace('.pkl', '_metadata.pkl')}")
        logger.info(f"[RandomForest] Model saved: {model_path}")

    def load_model(self, model_name: str = "random_forest_regime.pkl"):
        """Load Random Forest model"""
        model_path = self.model_dir / model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        self.model = joblib.load(model_path)

        metadata_path = self.model_dir / f"{model_name.replace('.pkl', '_metadata.pkl')}"
        if metadata_path.exists():
            metadata = joblib.load(metadata_path)
            self.best_params = metadata['best_params']
            self.feature_importance = pd.DataFrame(metadata['feature_importance']) if metadata['feature_importance'] else None
            self.n_classes = metadata['n_classes']
        logger.info(f"[RandomForest] Model loaded: {model_path}")
