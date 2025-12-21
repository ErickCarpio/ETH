"""
Main Orchestrator - Sistema Completo de Grid Trading con ML
Integra todos los módulos y ejecuta el ciclo de vida diario
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sys

# Imports de módulos locales
from data.managers.data_manager import DataManager
from weighting_logic import TemporalWeighting
from feature_engineering import FeatureEngineer
from target_labeling import RegimeLabeler
from model_pipeline import XGBoostRegimeModel
from execution_bot import GridExecutionBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_system.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TradingSystemOrchestrator:
    """
    Orquestador maestro del sistema de trading
    
    Ciclo de vida diario:
    1. Actualizar datos (ventana de 2 años)
    2. Calcular features
    3. Etiquetar régimen
    4. Calcular sample weights
    5. Re-entrenar modelo
    6. Predecir régimen actual
    7. Ejecutar/actualizar grid
    """
    
    def __init__(self, config: dict = None, config_file: str = None):
        """
        Args:
            config: Diccionario con configuración (opcional)
            config_file: Ruta a archivo YAML de configuración (opcional)
        """
        # Cargar configuración
        if config_file:
            from config_loader import ConfigLoader
            loader = ConfigLoader(config_file)
            self.config = loader.to_dict()
            loader.print_summary()
        elif config:
            self.config = config
        else:
            # Usar DEFAULT_CONFIG
            self.config = DEFAULT_CONFIG
        
        # Extraer configuraciones específicas
        risk_cfg = self.config.get('risk', {})
        data_cfg = self.config.get('data', {})
        weight_cfg = self.config.get('weighting', {})
        label_cfg = self.config.get('labeling', {})
        model_cfg = self.config.get('model', {})
        grid_cfg = self.config.get('grid', {})
        exchange_cfg = self.config.get('exchange', {})
        
        # Inicializar componentes
        self.data_manager = DataManager(
            symbol=exchange_cfg.get('symbol', 'ETH/USDT'),
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
        
        self.model = XGBoostRegimeModel(
            n_classes=model_cfg.get('n_classes', 4),
            optuna_trials=model_cfg.get('optuna_trials', 50),
            model_dir=model_cfg.get('model_dir', './models')
        )
        
        self.execution_bot = GridExecutionBot(
            symbol=exchange_cfg.get('symbol', 'ETH/USDT'),
            total_capital=risk_cfg.get('total_capital', 1000.0),
            grid_allocation=risk_cfg.get('grid_allocation', 0.8),
            min_order_value=risk_cfg.get('min_order_value', 20.0)
        )
        
        # Estado del sistema
        self.last_training_date = None
        self.current_dataset = None
        self.is_initialized = False
    
    async def initialize(self, api_key: str = None, secret: str = None):
        """
        Inicialización del sistema
        
        Args:
            api_key: API key del exchange (opcional)
            secret: Secret key del exchange (opcional)
        """
        logger.info("=" * 80)
        logger.info("INICIALIZANDO SISTEMA DE TRADING")
        logger.info("=" * 80)
        
        # Inicializar exchange
        await self.execution_bot.initialize_exchange(api_key, secret)
        
        # Primera carga completa de datos
        logger.info("\n1. Descargando datos históricos (2 años)...")
        
        # Obtener API keys si están disponibles
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
        
        # Construir features
        logger.info("\n2. Construyendo features...")
        features_df = self.feature_engineer.build_full_features(
            crypto_df=dataset['crypto'],
            macro_df=dataset['macro'],
            crypto_4h_df=dataset.get('crypto_4h'),  # Features macro de 4H
            onchain_df=dataset.get('onchain'),
            sentiment_df=dataset.get('sentiment'),
            defillama_df=dataset.get('defillama'),
            coinglass_df=dataset.get('coinglass')
        )
        
        # Etiquetar régimen (solo si se va a entrenar, skip si modelo existe)
        from pathlib import Path
        model_path = Path('models/xgboost_model.json')

        if model_path.exists():
            logger.info("\n3. ✓ Modelo existente encontrado - Saltando etiquetado de régimen")
            logger.info(f"   Modelo: {model_path}")
            self.current_dataset = features_df
        else:
            logger.info("\n3. Etiquetando régimen de mercado (primera vez)...")
            labeled_df = self.regime_labeler.label_regime(features_df)
            self.current_dataset = labeled_df

        self.is_initialized = True

        logger.info("\n✓ Sistema inicializado correctamente")
        logger.info(f"Dataset shape: {self.current_dataset.shape}")
        logger.info(f"Fecha más reciente: {self.current_dataset.index[-1]}")
    
    async def daily_update(self):
        """
        Actualización diaria del sistema
        
        Este método debe ejecutarse cada 24h vía cron job
        """
        logger.info("\n" + "=" * 80)
        logger.info(f"ACTUALIZACIÓN DIARIA - {datetime.now()}")
        logger.info("=" * 80)
        
        if not self.is_initialized:
            logger.error("Sistema no inicializado. Ejecutar .initialize() primero")
            return
        
        try:
            # 1. Actualizar datos (agregar nuevo día, eliminar más viejo)
            logger.info("\n1. Actualizando ventana de datos...")
            crypto_updated = await self.data_manager.update_daily(
                existing_df=self.current_dataset[['open','high','low','close','volume']]
            )
            
            macro_updated = self.data_manager.fetch_macro_data()
            
            # 2. Re-construir features
            logger.info("\n2. Re-construyendo features...")
            # Cargar crypto_4h desde caché para features macro
            crypto_4h_updated = self.data_manager._load_from_cache("prices_4h")

            features_df = self.feature_engineer.build_full_features(
                crypto_df=crypto_updated,
                macro_df=macro_updated,
                crypto_4h_df=crypto_4h_updated
            )
            
            # 3. Re-etiquetar régimen
            logger.info("\n3. Re-etiquetando régimen...")
            labeled_df = self.regime_labeler.label_regime(features_df)
            
            self.current_dataset = labeled_df
            
            logger.info("✓ Datos actualizados correctamente")
            
        except Exception as e:
            logger.error(f"Error en actualización de datos: {e}")
            raise
    
    async def retrain_model(self, quick_mode: bool = True):
        """
        Re-entrenamiento del modelo
        
        Args:
            quick_mode: Si True, usa optimización rápida (menos trials)
        """
        logger.info("\n" + "=" * 80)
        logger.info("RE-ENTRENAMIENTO DEL MODELO")
        logger.info("=" * 80)
        
        if self.current_dataset is None:
            logger.error("No hay datos para entrenar")
            return
        
        # Preparar datos
        feature_cols = self.feature_engineer.feature_names
        X = self.current_dataset[feature_cols]
        y = self.current_dataset['regime']
        
        # Calcular sample weights
        logger.info("\n1. Calculando sample weights temporales...")
        sample_weights = self.weighting.calculate_weights(self.current_dataset)
        
        # Split temporal (80% train, 20% validation)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        w_train = sample_weights[:split_idx]
        
        logger.info(f"Train set: {len(X_train)} samples")
        logger.info(f"Validation set: {len(X_val)} samples")
        
        # Entrenar
        logger.info("\n2. Entrenando modelo XGBoost...")
        self.model.retrain_daily(
            X_train,
            y_train,
            w_train,
            quick_optimization=quick_mode
        )
        
        # Validación
        logger.info("\n3. Validando modelo...")
        val_predictions = self.model.predict(X_val)
        val_proba = self.model.predict_proba(X_val)
        
        from sklearn.metrics import classification_report, accuracy_score
        
        accuracy = accuracy_score(y_val, val_predictions)
        logger.info(f"\nAccuracy en Validación: {accuracy:.4f}")
        logger.info("\nClassification Report:")
        print(classification_report(y_val, val_predictions))
        
        self.last_training_date = datetime.now()
        logger.info("\n✓ Re-entrenamiento completado")
    
    async def predict_current_regime(self) -> tuple:
        """
        Predice el régimen actual basado en los datos más recientes
        
        Returns:
            (predicted_regime, probabilities, current_price, volatility)
        """
        logger.info("\n" + "=" * 80)
        logger.info("PREDICCIÓN DE RÉGIMEN ACTUAL")
        logger.info("=" * 80)
        
        # Tomar última fila de features
        latest_data = self.current_dataset.iloc[[-1]]
        
        feature_cols = self.feature_engineer.feature_names
        X_current = latest_data[feature_cols]
        
        # Predecir
        regime_pred = self.model.predict(X_current)[0]
        regime_proba = self.model.predict_proba(X_current)[0]
        
        # Info adicional
        current_price = latest_data['close'].values[0]
        current_volatility = latest_data['volatility_24h'].values[0]
        
        regime_names = {
            0: 'LATERAL',
            1: 'ALCISTA',
            2: 'BAJISTA',
            3: 'PELIGRO'
        }
        
        logger.info(f"\nRégimen Predicho: {regime_pred} ({regime_names[regime_pred]})")
        logger.info(f"Confianza: {regime_proba[regime_pred]*100:.1f}%")
        logger.info(f"\nProbabilidades por clase:")
        for i, prob in enumerate(regime_proba):
            logger.info(f"  Clase {i} ({regime_names[i]}): {prob*100:.1f}%")
        
        logger.info(f"\nPrecio actual: ${current_price:.2f}")
        logger.info(f"Volatilidad (24h): {current_volatility*100:.2f}%")
        
        return regime_pred, regime_proba, current_price, current_volatility
    
    async def execute_trading_strategy(self):
        """
        Ejecuta estrategia de grid basada en régimen predicho
        """
        # Predecir régimen actual
        regime, proba, price, volatility = await self.predict_current_regime()
        
        # Ejecutar grid
        logger.info("\n" + "=" * 80)
        logger.info("EJECUCIÓN DE ESTRATEGIA")
        logger.info("=" * 80)
        
        await self.execution_bot.execute_regime_strategy(
            predicted_regime=regime,
            current_price=price,
            volatility=volatility
        )
    
    async def run_daily_cycle(self):
        """
        Ciclo completo diario (llamar vía cron)
        
        Flujo:
        1. Actualizar datos
        2. Re-entrenar modelo
        3. Predecir régimen
        4. Ejecutar/actualizar grid
        """
        logger.info("\n" + "=" * 80)
        logger.info("INICIO DE CICLO DIARIO COMPLETO")
        logger.info("=" * 80)
        
        try:
            # 1. Actualizar datos
            await self.daily_update()
            
            # 2. Re-entrenar modelo
            await self.retrain_model(quick_mode=True)
            
            # 3. Ejecutar estrategia
            await self.execute_trading_strategy()
            
            logger.info("\n" + "=" * 80)
            logger.info("✓ CICLO DIARIO COMPLETADO EXITOSAMENTE")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"\n❌ ERROR EN CICLO DIARIO: {e}")
            logger.exception("Stack trace:")
            raise
    
    async def shutdown(self):
        """Cierre limpio del sistema"""
        logger.info("\nCerrando sistema...")
        await self.execution_bot.close_exchange()
        logger.info("✓ Sistema cerrado")


# Configuración del sistema
DEFAULT_CONFIG = {
    'symbol': 'ETH/USDT',
    'data_window_years': 2,
    
    # Weighting
    'decay_rate': 0.001,
    'min_weight': 0.1,
    'max_weight': 1.0,
    'recent_days': 7,
    
    # Labeling
    'forward_window': 3,  # 12h
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
    Función principal para testing
    """
    # Crear sistema
    system = TradingSystemOrchestrator(DEFAULT_CONFIG)
    
    try:
        # Inicialización completa
        await system.initialize()
        
        # Simular primer entrenamiento
        await system.retrain_model(quick_mode=False)
        
        # Ejecutar predicción y estrategia
        await system.execute_trading_strategy()
        
        print("\n" + "=" * 80)
        print("TESTING COMPLETADO")
        print("=" * 80)
        print("\nPara PRODUCCIÓN:")
        print("1. Configurar API keys en .initialize(api_key, secret)")
        print("2. Programar cron job para ejecutar .run_daily_cycle() cada 24h")
        print("3. Monitorear logs en trading_system.log")
        
    finally:
        await system.shutdown()


if __name__ == "__main__":
    asyncio.run(main())