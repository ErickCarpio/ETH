"""
Main Orchestrator with Ensemble - Phase 6
Extended version of main_orchestrator.py with ensemble support

Supports both single model (XGBoost) and ensemble modes:
- simple_average: Average probabilities from all models
- weighted_voting: Weight models by validation performance
- stacking: CatBoost meta-learner on base model predictions
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sys
import argparse

# Imports from original orchestrator
from data.managers.data_manager import DataManager
from weighting_logic import TemporalWeighting
from feature_engineering import FeatureEngineer
from target_labeling import RegimeLabeler
from execution_bot import GridExecutionBot

# NEW: Ensemble imports
from ensemble_trainer import EnsembleTrainer
from model_pipeline import XGBoostRegimeModel  # Fallback to single model

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_system_ensemble.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TradingSystemOrchestratorEnsemble:
    """
    Enhanced orchestrator with ensemble support

    Modes:
    1. single_model: Use XGBoost only (original behavior)
    2. ensemble: Use ensemble of XGBoost, LightGBM, CatBoost, RandomForest

    Ensemble strategies:
    - simple_average: Average all model probabilities
    - weighted_voting: Weight by validation F1 score
    - stacking: CatBoost meta-learner
    """

    def __init__(
        self,
        config: dict = None,
        config_file: str = None,
        use_ensemble: bool = True,
        ensemble_strategy: str = "stacking"
    ):
        """
        Args:
            config: Configuration dictionary
            config_file: Path to YAML config file
            use_ensemble: If True, use ensemble; else use single XGBoost
            ensemble_strategy: 'simple_average', 'weighted_voting', or 'stacking'
        """
        # Load configuration
        if config_file:
            from config_loader import ConfigLoader
            loader = ConfigLoader(config_file)
            self.config = loader.to_dict()
            loader.print_summary()
        elif config:
            self.config = config
        else:
            self.config = DEFAULT_CONFIG

        # Ensemble configuration
        self.use_ensemble = use_ensemble
        self.ensemble_strategy = ensemble_strategy

        # Extract configs
        risk_cfg = self.config.get('risk', {})
        data_cfg = self.config.get('data', {})
        weight_cfg = self.config.get('weighting', {})
        label_cfg = self.config.get('labeling', {})
        model_cfg = self.config.get('model', {})
        grid_cfg = self.config.get('grid', {})
        exchange_cfg = self.config.get('exchange', {})

        # Initialize components
        self.data_manager = DataManager(
            symbol=exchange_cfg.get('symbol', 'ETHUSDT'),
            window_years=data_cfg.get('window_years', 2)
        )

        self.weighting = TemporalWeighting(
            decay_rate=weight_cfg.get('decay_rate', 0.001),
            min_weight=weight_cfg.get('min_weight', 0.1),
            max_weight=weight_cfg.get('max_weight', 1.0),
            recent_days=weight_cfg.get('recent_days', 7)
        )

        self.feature_engineer = FeatureEngineer()

        self.regime_labeler = RegimeLabeler(
            forward_window=label_cfg.get('forward_window', 3),
            volatility_threshold_low=label_cfg.get('vol_threshold_low', 0.015),
            volatility_threshold_high=label_cfg.get('vol_threshold_high', 0.05),
            trend_threshold=label_cfg.get('trend_threshold', 0.02)
        )

        # Model: Ensemble or Single
        if self.use_ensemble:
            logger.info(f"Using ENSEMBLE mode with strategy: {self.ensemble_strategy}")
            self.model = EnsembleTrainer(
                n_classes=model_cfg.get('n_classes', 4),
                optuna_trials=model_cfg.get('optuna_trials', 50),
                model_dir=model_cfg.get('model_dir', './models'),
                ensemble_strategy=self.ensemble_strategy
            )
        else:
            logger.info("Using SINGLE MODEL mode (XGBoost)")
            self.model = XGBoostRegimeModel(
                n_classes=model_cfg.get('n_classes', 4),
                optuna_trials=model_cfg.get('optuna_trials', 50),
                model_dir=model_cfg.get('model_dir', './models')
            )

        self.execution_bot = GridExecutionBot(
            symbol=exchange_cfg.get('symbol', 'ETHUSDT'),
            total_capital=risk_cfg.get('total_capital', 1000.0),
            grid_allocation=risk_cfg.get('grid_allocation', 0.8),
            min_order_value=risk_cfg.get('min_order_value', 20.0)
        )

        # State
        self.last_training_date = None
        self.current_dataset = None
        self.is_initialized = False

    async def initialize(self, api_key: str = None, secret: str = None):
        """Initialize system"""
        logger.info("=" * 80)
        logger.info("INITIALIZING TRADING SYSTEM (WITH ENSEMBLE)")
        logger.info("=" * 80)
        logger.info(f"Ensemble mode: {self.use_ensemble}")
        if self.use_ensemble:
            logger.info(f"Ensemble strategy: {self.ensemble_strategy}")

        # Initialize exchange
        await self.execution_bot.initialize_exchange(api_key, secret)

        # Load data
        logger.info("\n1. Loading historical data (2 years)...")

        # Get API keys if available
        api_keys = {}
        if 'external_apis' in self.config:
            apis = self.config['external_apis']
            if apis.get('cryptoquant', {}).get('enabled'):
                api_keys['cryptoquant'] = apis['cryptoquant'].get('api_key')
            if apis.get('glassnode', {}).get('enabled'):
                api_keys['glassnode'] = apis['glassnode'].get('api_key')
            if apis.get('newsapi', {}).get('enabled'):
                api_keys['newsapi'] = apis['newsapi'].get('api_key')
            if apis.get('cryptopanic', {}).get('enabled'):
                api_keys['cryptopanic'] = apis['cryptopanic'].get('api_key')

        dataset = await self.data_manager.get_full_dataset(
            include_onchain=self.config.get('data', {}).get('include_onchain', False),
            include_sentiment=self.config.get('data', {}).get('include_sentiment', False),
            api_keys=api_keys if api_keys else None
        )

        # Build features (176 features from Phases 1-5)
        logger.info("\n2. Building features (Phase 1-5: 176 features)...")
        features_df = self.feature_engineer.build_full_features(
            crypto_df=dataset['crypto'],
            macro_df=dataset['macro'],
            onchain_df=dataset.get('onchain'),
            sentiment_df=dataset.get('sentiment'),
            defillama_df=dataset.get('defillama'),
            coinglass_df=dataset.get('coinglass'),
            microstructure_df=dataset.get('microstructure'),
            derivatives_df=dataset.get('derivatives')
        )

        logger.info(f"Total features: {len(features_df.columns)}")

        # Label regime
        logger.info("\n3. Labeling market regime...")
        labeled_df = self.regime_labeler.label_regime(features_df)

        self.current_dataset = labeled_df
        self.is_initialized = True

        logger.info("\n✓ System initialized")
        logger.info(f"Dataset shape: {self.current_dataset.shape}")
        logger.info(f"Most recent date: {self.current_dataset.index[-1]}")

    async def retrain_model(self, quick_mode: bool = True):
        """
        Re-train model (ensemble or single)

        Args:
            quick_mode: If True, use fewer Optuna trials
        """
        logger.info("\n" + "=" * 80)
        logger.info("RE-TRAINING MODEL")
        if self.use_ensemble:
            logger.info(f"Ensemble Strategy: {self.ensemble_strategy}")
        logger.info("=" * 80)

        if self.current_dataset is None:
            logger.error("No data to train")
            return

        # Prepare data
        feature_cols = self.feature_engineer.feature_names
        X = self.current_dataset[feature_cols]
        y = self.current_dataset['regime']

        # Calculate sample weights
        logger.info("\n1. Calculating temporal + class balanced weights...")
        sample_weights = self.weighting.calculate_weights(self.current_dataset)

        # Split temporal (80% train, 20% validation)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        w_train = sample_weights[:split_idx]

        logger.info(f"Train set: {len(X_train)} samples")
        logger.info(f"Validation set: {len(X_val)} samples")

        # Train
        if self.use_ensemble:
            logger.info("\n2. Training ensemble (4 base models + ensemble strategy)...")

            # Adjust trials for quick mode
            if quick_mode:
                original_trials = self.model.optuna_trials
                self.model.optuna_trials = 20

            # Train ensemble
            self.model.train_ensemble(
                X_train, y_train, w_train,
                X_val, y_val,
                optimize_base_models=not quick_mode
            )

            # Restore trials
            if quick_mode:
                self.model.optuna_trials = original_trials

            # Feature importance summary
            logger.info("\n3. Feature Importance Summary (averaged across models):")
            importance_df = self.model.get_feature_importance_summary()
            if not importance_df.empty:
                logger.info(f"\n{importance_df.head(10).to_string(index=False)}")

        else:
            logger.info("\n2. Training single XGBoost model...")
            self.model.train(
                X_train, y_train, w_train,
                X_val=X_val, y_val=y_val,
                optimize=not quick_mode
            )

        self.last_training_date = datetime.now()
        logger.info("\n✓ Re-training completed")

    async def predict_current_regime(self) -> tuple:
        """
        Predict current regime using ensemble or single model

        Returns:
            (predicted_regime, probabilities, current_price, volatility)
        """
        logger.info("\n" + "=" * 80)
        logger.info("PREDICTING CURRENT REGIME")
        if self.use_ensemble:
            logger.info(f"Using Ensemble ({self.ensemble_strategy})")
        logger.info("=" * 80)

        # Get latest data
        latest_data = self.current_dataset.iloc[[-1]]

        feature_cols = self.feature_engineer.feature_names
        X_current = latest_data[feature_cols]

        # Predict
        regime_pred = self.model.predict(X_current)[0]
        regime_proba = self.model.predict_proba(X_current)[0]

        # Additional info
        current_price = latest_data['close'].values[0]
        current_volatility = latest_data['volatility_24h'].values[0]

        regime_names = {
            0: 'LATERAL',
            1: 'ALCISTA',
            2: 'BAJISTA',
            3: 'PELIGRO'
        }

        logger.info(f"\nPredicted Regime: {regime_pred} ({regime_names[regime_pred]})")
        logger.info(f"Confidence: {regime_proba[regime_pred]*100:.1f}%")
        logger.info(f"\nClass Probabilities:")
        for i, prob in enumerate(regime_proba):
            logger.info(f"  Class {i} ({regime_names[i]}): {prob*100:.1f}%")

        logger.info(f"\nCurrent Price: ${current_price:.2f}")
        logger.info(f"Volatility (24h): {current_volatility*100:.2f}%")

        return regime_pred, regime_proba, current_price, current_volatility

    async def execute_trading_strategy(self):
        """Execute grid trading strategy based on predicted regime"""
        # Predict regime
        regime, proba, price, volatility = await self.predict_current_regime()

        # Execute grid
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTING TRADING STRATEGY")
        logger.info("=" * 80)

        await self.execution_bot.execute_regime_strategy(
            predicted_regime=regime,
            current_price=price,
            volatility=volatility
        )

    async def daily_update(self):
        """Daily data update"""
        logger.info("\n" + "=" * 80)
        logger.info(f"DAILY UPDATE - {datetime.now()}")
        logger.info("=" * 80)

        if not self.is_initialized:
            logger.error("System not initialized")
            return

        try:
            # Update data
            logger.info("\n1. Updating data window...")
            crypto_updated = await self.data_manager.update_daily(
                existing_df=self.current_dataset[['open','high','low','close','volume']]
            )

            macro_updated = self.data_manager.fetch_macro_data()

            # Re-build features
            logger.info("\n2. Re-building features...")
            features_df = self.feature_engineer.build_full_features(
                crypto_df=crypto_updated,
                macro_df=macro_updated
            )

            # Re-label regime
            logger.info("\n3. Re-labeling regime...")
            labeled_df = self.regime_labeler.label_regime(features_df)

            self.current_dataset = labeled_df

            logger.info("✓ Data updated")

        except Exception as e:
            logger.error(f"Error updating data: {e}")
            raise

    async def run_daily_cycle(self):
        """Complete daily cycle"""
        logger.info("\n" + "=" * 80)
        logger.info("STARTING DAILY CYCLE")
        logger.info("=" * 80)

        try:
            # 1. Update data
            await self.daily_update()

            # 2. Re-train model
            await self.retrain_model(quick_mode=True)

            # 3. Execute strategy
            await self.execute_trading_strategy()

            logger.info("\n" + "=" * 80)
            logger.info("✓ DAILY CYCLE COMPLETED")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"\n❌ ERROR IN DAILY CYCLE: {e}")
            logger.exception("Stack trace:")
            raise

    async def shutdown(self):
        """Clean shutdown"""
        logger.info("\nShutting down system...")
        await self.execution_bot.close_exchange()
        logger.info("✓ System closed")


# Default configuration
DEFAULT_CONFIG = {
    'symbol': 'ETHUSDT',
    'data_window_years': 2,

    # Weighting
    'decay_rate': 0.001,
    'min_weight': 0.1,
    'max_weight': 1.0,
    'recent_days': 7,

    # Labeling
    'forward_window': 3,
    'vol_threshold_low': 0.015,
    'vol_threshold_high': 0.05,
    'trend_threshold': 0.02,

    # Model
    'n_classes': 4,
    'optuna_trials': 50,
    'model_dir': './models',

    # Execution
    'total_capital': 10000,
    'grid_allocation': 0.8
}


async def main():
    """
    Main function for testing ensemble

    Usage:
        # Single model (XGBoost only)
        python main_orchestrator_ensemble.py --mode single

        # Ensemble with simple averaging
        python main_orchestrator_ensemble.py --mode ensemble --strategy simple_average

        # Ensemble with weighted voting
        python main_orchestrator_ensemble.py --mode ensemble --strategy weighted_voting

        # Ensemble with stacking (recommended)
        python main_orchestrator_ensemble.py --mode ensemble --strategy stacking
    """
    # Parse arguments
    parser = argparse.ArgumentParser(description='Trading System with Ensemble Support')
    parser.add_argument('--mode', type=str, default='ensemble', choices=['single', 'ensemble'],
                       help='single: XGBoost only, ensemble: 4 models')
    parser.add_argument('--strategy', type=str, default='stacking',
                       choices=['simple_average', 'weighted_voting', 'stacking'],
                       help='Ensemble strategy')
    parser.add_argument('--quick', action='store_true',
                       help='Quick mode (fewer Optuna trials)')

    args = parser.parse_args()

    use_ensemble = (args.mode == 'ensemble')

    # Create system
    system = TradingSystemOrchestratorEnsemble(
        config=DEFAULT_CONFIG,
        use_ensemble=use_ensemble,
        ensemble_strategy=args.strategy
    )

    try:
        # Initialize
        await system.initialize()

        # Train
        await system.retrain_model(quick_mode=args.quick)

        # Predict and execute
        await system.execute_trading_strategy()

        print("\n" + "=" * 80)
        print("TESTING COMPLETED")
        print("=" * 80)
        print(f"\nMode: {args.mode}")
        if use_ensemble:
            print(f"Strategy: {args.strategy}")
        print("\nFor PRODUCTION:")
        print("1. Configure API keys in .initialize(api_key, secret)")
        print("2. Schedule cron job for .run_daily_cycle() every 24h")
        print("3. Monitor logs in trading_system_ensemble.log")

    finally:
        await system.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
