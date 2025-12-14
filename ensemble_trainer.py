"""
Ensemble Trainer - Phase 6
Implements 3 ensemble strategies for regime classification:
1. Simple Averaging - Average probabilities from all models
2. Weighted Voting - Weight models by validation performance
3. Stacking - Use CatBoost meta-learner on base model predictions

Expected improvement: +2-4 pp → 76-80% accuracy
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging
from pathlib import Path
import joblib
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, f1_score, classification_report
from catboost import CatBoostClassifier

from ensemble_models import (
    BaseRegimeModel,
    XGBoostModel,
    LightGBMModel,
    CatBoostModel,
    RandomForestModel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnsembleTrainer:
    """
    Ensemble trainer with multiple strategies

    Strategies:
    1. simple_average: Average probabilities from all models
    2. weighted_voting: Weight models by validation F1 score
    3. stacking: Train meta-learner on base model predictions
    """

    def __init__(
        self,
        n_classes: int = 4,
        optuna_trials: int = 50,
        model_dir: str = "./models",
        ensemble_strategy: str = "stacking"
    ):
        """
        Args:
            n_classes: Number of regime classes (4)
            optuna_trials: Number of Optuna trials for optimization
            model_dir: Directory to save/load models
            ensemble_strategy: 'simple_average', 'weighted_voting', or 'stacking'
        """
        self.n_classes = n_classes
        self.optuna_trials = optuna_trials
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True, parents=True)
        self.ensemble_strategy = ensemble_strategy

        # Initialize base models
        self.base_models = {
            'xgboost': XGBoostModel(n_classes, optuna_trials, model_dir),
            'lightgbm': LightGBMModel(n_classes, optuna_trials, model_dir),
            'catboost': CatBoostModel(n_classes, optuna_trials, model_dir),
            'random_forest': RandomForestModel(n_classes, optuna_trials, model_dir)
        }

        # Meta-learner for stacking (CatBoost)
        self.meta_learner = None

        # Model weights for weighted voting
        self.model_weights = {}

        # Validation performance
        self.validation_scores = {}

    def train_base_models(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        sample_weights: np.ndarray,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
        optimize: bool = True
    ):
        """
        Train all base models

        Args:
            X_train: Training features
            y_train: Training labels
            sample_weights: Temporal + class balanced weights
            X_val: Validation features (optional)
            y_val: Validation labels (optional)
            optimize: Whether to optimize hyperparameters
        """
        logger.info("=" * 80)
        logger.info("PHASE 6: ENSEMBLE TRAINING - BASE MODELS")
        logger.info("=" * 80)

        for model_name, model in self.base_models.items():
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Training {model_name.upper()}")
            logger.info(f"{'=' * 80}")

            # Train model
            model.train(
                X_train, y_train, sample_weights,
                X_val=X_val, y_val=y_val,
                optimize=optimize
            )

            # Calculate validation score for weighting
            if X_val is not None and y_val is not None:
                y_val_pred = model.predict(X_val)
                f1 = f1_score(y_val, y_val_pred, average='weighted')
                accuracy = accuracy_score(y_val, y_val_pred)

                self.validation_scores[model_name] = {
                    'f1': f1,
                    'accuracy': accuracy
                }

                logger.info(f"[{model_name}] Validation F1: {f1:.4f}, Accuracy: {accuracy:.4f}")

            # Save base model
            model.save_model()

        logger.info("\n" + "=" * 80)
        logger.info("✓ All base models trained successfully")
        logger.info("=" * 80)

    def _get_base_predictions(
        self,
        X: pd.DataFrame,
        return_proba: bool = False
    ) -> Dict[str, np.ndarray]:
        """
        Get predictions from all base models

        Args:
            X: Features
            return_proba: If True, return probabilities; else return class labels

        Returns:
            Dictionary mapping model_name -> predictions
        """
        predictions = {}

        for model_name, model in self.base_models.items():
            if return_proba:
                predictions[model_name] = model.predict_proba(X)
            else:
                predictions[model_name] = model.predict(X)

        return predictions

    def train_ensemble_simple_average(self):
        """
        Simple average ensemble - no additional training needed
        Just average probabilities from all base models
        """
        logger.info("\n" + "=" * 80)
        logger.info("ENSEMBLE STRATEGY: Simple Average")
        logger.info("=" * 80)
        logger.info("No additional training needed - will average probabilities at prediction time")

    def train_ensemble_weighted_voting(self, X_val: pd.DataFrame, y_val: pd.Series):
        """
        Weighted voting ensemble
        Weight models by their validation F1 score

        Args:
            X_val: Validation features
            y_val: Validation labels
        """
        logger.info("\n" + "=" * 80)
        logger.info("ENSEMBLE STRATEGY: Weighted Voting")
        logger.info("=" * 80)

        # Calculate weights based on F1 scores
        total_f1 = sum([scores['f1'] for scores in self.validation_scores.values()])

        for model_name, scores in self.validation_scores.items():
            weight = scores['f1'] / total_f1
            self.model_weights[model_name] = weight
            logger.info(f"[{model_name}] Weight: {weight:.4f} (F1: {scores['f1']:.4f})")

        # Test ensemble on validation set
        predictions_proba = self._get_base_predictions(X_val, return_proba=True)

        # Weighted average of probabilities
        ensemble_proba = np.zeros((len(X_val), self.n_classes))
        for model_name, proba in predictions_proba.items():
            ensemble_proba += proba * self.model_weights[model_name]

        ensemble_pred = np.argmax(ensemble_proba, axis=1)

        # Evaluate ensemble
        f1 = f1_score(y_val, ensemble_pred, average='weighted')
        accuracy = accuracy_score(y_val, ensemble_pred)

        logger.info(f"\n[Weighted Voting Ensemble] Validation F1: {f1:.4f}, Accuracy: {accuracy:.4f}")

        # Save weights
        joblib.dump(self.model_weights, self.model_dir / "weighted_voting_weights.pkl")

    def train_ensemble_stacking(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        sample_weights: np.ndarray,
        X_val: pd.DataFrame,
        y_val: pd.Series
    ):
        """
        Stacking ensemble with CatBoost meta-learner

        Strategy:
        1. Get out-of-fold predictions from base models on training data
        2. Train meta-learner on these predictions
        3. Final prediction = meta-learner(base_model_predictions)

        Args:
            X_train: Training features
            y_train: Training labels
            sample_weights: Temporal + class balanced weights
            X_val: Validation features
            y_val: Validation labels
        """
        logger.info("\n" + "=" * 80)
        logger.info("ENSEMBLE STRATEGY: Stacking with CatBoost Meta-Learner")
        logger.info("=" * 80)

        # Step 1: Generate out-of-fold predictions for training data
        logger.info("\n1. Generating out-of-fold predictions from base models...")

        n_samples = len(X_train)
        oof_predictions = np.zeros((n_samples, len(self.base_models) * self.n_classes))

        # Use TimeSeriesSplit for out-of-fold predictions
        tscv = TimeSeriesSplit(n_splits=5)

        for model_name, model in self.base_models.items():
            logger.info(f"   Generating OOF predictions for {model_name}...")

            model_oof = np.zeros((n_samples, self.n_classes))

            for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X_train)):
                # Train on fold
                X_fold_train = X_train.iloc[train_idx]
                y_fold_train = y_train.iloc[train_idx]
                w_fold_train = sample_weights[train_idx]

                X_fold_val = X_train.iloc[val_idx]

                # Create temporary model for this fold
                if model_name == 'xgboost':
                    fold_model = XGBoostModel(self.n_classes, self.optuna_trials // 2, self.model_dir)
                elif model_name == 'lightgbm':
                    fold_model = LightGBMModel(self.n_classes, self.optuna_trials // 2, self.model_dir)
                elif model_name == 'catboost':
                    fold_model = CatBoostModel(self.n_classes, self.optuna_trials // 2, self.model_dir)
                else:  # random_forest
                    fold_model = RandomForestModel(self.n_classes, self.optuna_trials // 2, self.model_dir)

                # Train without optimization (use base model's params)
                if model.best_params is not None:
                    fold_model.best_params = model.best_params
                    fold_model.train(X_fold_train, y_fold_train, w_fold_train, optimize=False)
                else:
                    fold_model.train(X_fold_train, y_fold_train, w_fold_train, optimize=True)

                # Predict on validation fold
                model_oof[val_idx] = fold_model.predict_proba(X_fold_val)

            # Store OOF predictions for this model
            start_col = list(self.base_models.keys()).index(model_name) * self.n_classes
            end_col = start_col + self.n_classes
            oof_predictions[:, start_col:end_col] = model_oof

        # Step 2: Train meta-learner on OOF predictions
        logger.info("\n2. Training CatBoost meta-learner on OOF predictions...")

        self.meta_learner = CatBoostClassifier(
            iterations=300,
            learning_rate=0.05,
            depth=4,
            loss_function='MultiClass',
            eval_metric='TotalF1:average=Weighted',
            random_seed=42,
            verbose=False
        )

        # Train meta-learner
        self.meta_learner.fit(
            oof_predictions,
            y_train,
            sample_weight=sample_weights,
            verbose=False
        )

        # Step 3: Evaluate on validation set
        logger.info("\n3. Evaluating stacking ensemble on validation set...")

        # Get base model predictions on validation set
        val_predictions = self._get_base_predictions(X_val, return_proba=True)

        # Stack predictions
        val_stacked = np.column_stack([val_predictions[name] for name in self.base_models.keys()])

        # Meta-learner prediction
        ensemble_pred = self.meta_learner.predict(val_stacked)
        ensemble_proba = self.meta_learner.predict_proba(val_stacked)

        # Evaluate
        f1 = f1_score(y_val, ensemble_pred, average='weighted')
        accuracy = accuracy_score(y_val, ensemble_pred)

        logger.info(f"\n[Stacking Ensemble] Validation F1: {f1:.4f}, Accuracy: {accuracy:.4f}")

        # Detailed report
        logger.info("\nClassification Report:")
        print(classification_report(y_val, ensemble_pred, zero_division=0))

        # Save meta-learner
        self.meta_learner.save_model(str(self.model_dir / "stacking_meta_learner.cbm"))
        logger.info(f"\nMeta-learner saved: {self.model_dir / 'stacking_meta_learner.cbm'}")

    def train_ensemble(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        sample_weights: np.ndarray,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        optimize_base_models: bool = True
    ):
        """
        Complete ensemble training pipeline

        Args:
            X_train: Training features
            y_train: Training labels
            sample_weights: Temporal + class balanced weights
            X_val: Validation features
            y_val: Validation labels
            optimize_base_models: Whether to optimize base model hyperparameters
        """
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 6: ENSEMBLE TRAINING - COMPLETE PIPELINE")
        logger.info("=" * 80)
        logger.info(f"Strategy: {self.ensemble_strategy}")
        logger.info(f"Base models: {list(self.base_models.keys())}")
        logger.info(f"Training samples: {len(X_train)}")
        logger.info(f"Validation samples: {len(X_val)}")
        logger.info(f"Features: {len(X_train.columns)}")

        # Step 1: Train base models
        self.train_base_models(
            X_train, y_train, sample_weights,
            X_val=X_val, y_val=y_val,
            optimize=optimize_base_models
        )

        # Step 2: Train ensemble based on strategy
        if self.ensemble_strategy == "simple_average":
            self.train_ensemble_simple_average()

        elif self.ensemble_strategy == "weighted_voting":
            self.train_ensemble_weighted_voting(X_val, y_val)

        elif self.ensemble_strategy == "stacking":
            self.train_ensemble_stacking(X_train, y_train, sample_weights, X_val, y_val)

        else:
            raise ValueError(f"Unknown ensemble strategy: {self.ensemble_strategy}")

        logger.info("\n" + "=" * 80)
        logger.info("✓ ENSEMBLE TRAINING COMPLETE")
        logger.info("=" * 80)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict using ensemble

        Args:
            X: Features

        Returns:
            Predicted class labels
        """
        if self.ensemble_strategy == "simple_average":
            return self._predict_simple_average(X)
        elif self.ensemble_strategy == "weighted_voting":
            return self._predict_weighted_voting(X)
        elif self.ensemble_strategy == "stacking":
            return self._predict_stacking(X)
        else:
            raise ValueError(f"Unknown ensemble strategy: {self.ensemble_strategy}")

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict probabilities using ensemble

        Args:
            X: Features

        Returns:
            Predicted class probabilities (n_samples, n_classes)
        """
        if self.ensemble_strategy == "simple_average":
            return self._predict_proba_simple_average(X)
        elif self.ensemble_strategy == "weighted_voting":
            return self._predict_proba_weighted_voting(X)
        elif self.ensemble_strategy == "stacking":
            return self._predict_proba_stacking(X)
        else:
            raise ValueError(f"Unknown ensemble strategy: {self.ensemble_strategy}")

    def _predict_simple_average(self, X: pd.DataFrame) -> np.ndarray:
        """Simple average of all base model predictions"""
        proba = self._predict_proba_simple_average(X)
        return np.argmax(proba, axis=1)

    def _predict_proba_simple_average(self, X: pd.DataFrame) -> np.ndarray:
        """Simple average of all base model probabilities"""
        predictions_proba = self._get_base_predictions(X, return_proba=True)

        # Average probabilities
        avg_proba = np.mean([proba for proba in predictions_proba.values()], axis=0)
        return avg_proba

    def _predict_weighted_voting(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted voting prediction"""
        proba = self._predict_proba_weighted_voting(X)
        return np.argmax(proba, axis=1)

    def _predict_proba_weighted_voting(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted average of base model probabilities"""
        predictions_proba = self._get_base_predictions(X, return_proba=True)

        # Weighted average
        weighted_proba = np.zeros((len(X), self.n_classes))
        for model_name, proba in predictions_proba.items():
            weighted_proba += proba * self.model_weights[model_name]

        return weighted_proba

    def _predict_stacking(self, X: pd.DataFrame) -> np.ndarray:
        """Stacking prediction using meta-learner"""
        if self.meta_learner is None:
            raise ValueError("Meta-learner not trained. Call train_ensemble() first.")

        # Get base model predictions
        predictions_proba = self._get_base_predictions(X, return_proba=True)

        # Stack predictions
        stacked = np.column_stack([predictions_proba[name] for name in self.base_models.keys()])

        # Meta-learner prediction
        return self.meta_learner.predict(stacked)

    def _predict_proba_stacking(self, X: pd.DataFrame) -> np.ndarray:
        """Stacking probability prediction using meta-learner"""
        if self.meta_learner is None:
            raise ValueError("Meta-learner not trained. Call train_ensemble() first.")

        # Get base model predictions
        predictions_proba = self._get_base_predictions(X, return_proba=True)

        # Stack predictions
        stacked = np.column_stack([predictions_proba[name] for name in self.base_models.keys()])

        # Meta-learner probability prediction
        return self.meta_learner.predict_proba(stacked)

    def get_feature_importance_summary(self) -> pd.DataFrame:
        """
        Get aggregated feature importance from all base models

        Returns:
            DataFrame with feature importance averaged across models
        """
        all_importances = []

        for model_name, model in self.base_models.items():
            if model.feature_importance is not None:
                imp_df = model.feature_importance.copy()
                imp_df['model'] = model_name
                all_importances.append(imp_df)

        if not all_importances:
            return pd.DataFrame()

        # Concatenate all
        combined = pd.concat(all_importances, ignore_index=True)

        # Average importance per feature
        avg_importance = combined.groupby('feature')['importance'].mean().reset_index()
        avg_importance = avg_importance.sort_values('importance', ascending=False)

        return avg_importance

    def load_ensemble(self):
        """Load pre-trained ensemble"""
        logger.info("Loading pre-trained ensemble...")

        # Load base models
        for model_name, model in self.base_models.items():
            try:
                if model_name == 'xgboost':
                    model.load_model("xgboost_regime.json")
                elif model_name == 'lightgbm':
                    model.load_model("lightgbm_regime.txt")
                elif model_name == 'catboost':
                    model.load_model("catboost_regime.cbm")
                elif model_name == 'random_forest':
                    model.load_model("random_forest_regime.pkl")
            except FileNotFoundError:
                logger.warning(f"[{model_name}] Model file not found, skipping...")

        # Load ensemble-specific components
        if self.ensemble_strategy == "weighted_voting":
            weights_path = self.model_dir / "weighted_voting_weights.pkl"
            if weights_path.exists():
                self.model_weights = joblib.load(weights_path)
                logger.info("Weighted voting weights loaded")

        elif self.ensemble_strategy == "stacking":
            meta_path = self.model_dir / "stacking_meta_learner.cbm"
            if meta_path.exists():
                self.meta_learner = CatBoostClassifier()
                self.meta_learner.load_model(str(meta_path))
                logger.info("Stacking meta-learner loaded")

        logger.info("✓ Ensemble loaded successfully")
