"""
Config Loader - Carga y valida configuración desde YAML
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Carga configuración desde archivo YAML y variables de entorno
    Prioridad: ENV VARS > YAML > DEFAULTS
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Args:
            config_path: Ruta al archivo de configuración
        """
        self.config_path = Path(config_path)
        self.config = {}
        
        if self.config_path.exists():
            self._load_from_yaml()
        else:
            logger.warning(f"Archivo de configuración no encontrado: {config_path}")
            logger.info("Usando configuración por defecto")
            self._load_defaults()
        
        # Sobreescribir con variables de entorno
        self._override_with_env_vars()
        
        # Validar configuración
        self._validate_config()
    
    def _load_from_yaml(self):
        """Carga configuración desde YAML"""
        logger.info(f"Cargando configuración desde: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        logger.info("✓ Configuración cargada desde YAML")
    
    def _load_defaults(self):
        """Configuración por defecto si no existe archivo"""
        self.config = {
            'exchange': {
                'name': 'binance',
                'symbol': 'ETH/USDT',
                'testnet': True
            },
            'risk': {
                'total_capital': 1000.0,
                'grid_allocation': 0.80,
                'min_order_value': 20.0
            },
            'data': {
                'window_years': 2,
                'timeframe': '4h',
                'include_onchain': False,
                'include_sentiment': False
            },
            'weighting': {
                'decay_rate': 0.001,
                'min_weight': 0.1,
                'max_weight': 1.0,
                'recent_days': 7
            },
            'labeling': {
                'forward_window': 3,
                'vol_threshold_low': 0.015,
                'vol_threshold_high': 0.05,
                'trend_threshold': 0.02
            },
            'model': {
                'n_classes': 4,
                'optuna_trials': 50,
                'quick_retrain_trials': 20,
                'model_dir': './models'
            },
            'grid': {
                'min_spacing': 0.005,
                'max_spacing': 0.03,
                'max_duration_hours': 72
            },
            'dev': {
                'use_simulated_data': True,
                'paper_trading': True
            }
        }
    
    def _override_with_env_vars(self):
        """
        Sobreescribe configuración con variables de entorno
        Formato: TRADING_SECTION_KEY (ejemplo: TRADING_EXCHANGE_API_KEY)
        """
        env_mappings = {
            'TRADING_BINANCE_API_KEY': ['exchange', 'api_key'],
            'TRADING_BINANCE_SECRET': ['exchange', 'secret'],
            'TRADING_CAPITAL': ['risk', 'total_capital'],
            'TRADING_TESTNET': ['exchange', 'testnet'],
            'TRADING_CRYPTOQUANT_KEY': ['external_apis', 'cryptoquant', 'api_key'],
            'TRADING_GLASSNODE_KEY': ['external_apis', 'glassnode', 'api_key'],
            'TRADING_NEWSAPI_KEY': ['external_apis', 'newsapi', 'api_key'],
        }
        
        for env_var, path in env_mappings.items():
            value = os.getenv(env_var)
            
            if value is not None:
                # Navegar al nivel correcto y asignar valor
                current = self.config
                for key in path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # Convertir tipos si es necesario
                if path[-1] in ['total_capital', 'min_order_value']:
                    value = float(value)
                elif path[-1] == 'testnet':
                    value = value.lower() in ('true', '1', 'yes')
                
                current[path[-1]] = value
                logger.info(f"✓ Variable de entorno aplicada: {env_var}")
    
    def _validate_config(self):
        """Valida que la configuración sea correcta"""
        logger.info("Validando configuración...")
        
        # Validar capital
        capital = self.get('risk.total_capital')
        if capital <= 0:
            raise ValueError(f"Capital debe ser > 0, encontrado: {capital}")
        
        min_order = self.get('risk.min_order_value')
        if min_order < 10:
            logger.warning(f"⚠️ Orden mínima muy baja: ${min_order}. Binance requiere ~$10-$20")
        
        # Validar que min_order no exceda capital disponible
        grid_allocation = self.get('risk.grid_allocation')
        available = capital * grid_allocation
        
        if min_order > available:
            raise ValueError(
                f"Orden mínima (${min_order}) > Capital disponible (${available:.2f})"
            )
        
        # Validar API keys si no es modo simulación
        if not self.get('dev.use_simulated_data'):
            if not self.get('exchange.api_key'):
                logger.warning("⚠️ Sin API key de exchange. Usando modo simulación.")
                self.config['dev']['use_simulated_data'] = True
        
        logger.info("✓ Configuración validada")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene valor de configuración usando notación de punto
        
        Args:
            key: Clave en formato 'section.subsection.key'
            default: Valor por defecto si no existe
        
        Returns:
            Valor de configuración
        
        Example:
            config.get('risk.total_capital')  # 1000.0
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_exchange_config(self) -> Dict:
        """Retorna configuración de exchange lista para usar"""
        exchange_cfg = self.config.get('exchange', {})
        
        # Seleccionar keys según testnet/producción
        if exchange_cfg.get('testnet'):
            api_key = exchange_cfg.get('testnet_api_key')
            secret = exchange_cfg.get('testnet_secret')
        else:
            api_key = exchange_cfg.get('api_key')
            secret = exchange_cfg.get('secret')
        
        return {
            'symbol': exchange_cfg.get('symbol', 'ETH/USDT'),
            'api_key': api_key,
            'secret': secret,
            'testnet': exchange_cfg.get('testnet', True)
        }
    
    def get_api_keys(self) -> Dict[str, str]:
        """Retorna todas las API keys externas"""
        apis = self.config.get('external_apis', {})
        
        keys = {}
        
        if apis.get('cryptoquant', {}).get('enabled'):
            keys['cryptoquant'] = apis['cryptoquant'].get('api_key')
        
        if apis.get('glassnode', {}).get('enabled'):
            keys['glassnode'] = apis['glassnode'].get('api_key')
        
        if apis.get('newsapi', {}).get('enabled'):
            keys['newsapi'] = apis['newsapi'].get('api_key')
        
        return keys
    
    def to_dict(self) -> Dict:
        """Retorna configuración completa como diccionario"""
        return self.config.copy()
    
    def print_summary(self):
        """Imprime resumen de configuración (sin mostrar secrets)"""
        logger.info("\n" + "=" * 70)
        logger.info("RESUMEN DE CONFIGURACIÓN")
        logger.info("=" * 70)
        
        logger.info(f"\n📊 EXCHANGE:")
        logger.info(f"  Symbol: {self.get('exchange.symbol')}")
        logger.info(f"  Testnet: {self.get('exchange.testnet')}")
        logger.info(f"  API Key: {'✓ Configurada' if self.get('exchange.api_key') else '✗ Faltante'}")
        
        logger.info(f"\n💰 RIESGO:")
        logger.info(f"  Capital Total: ${self.get('risk.total_capital'):.2f}")
        logger.info(f"  Grid Allocation: {self.get('risk.grid_allocation')*100:.0f}%")
        logger.info(f"  Min Order Value: ${self.get('risk.min_order_value'):.2f}")
        
        logger.info(f"\n📈 DATOS:")
        logger.info(f"  Ventana: {self.get('data.window_years')} años")
        logger.info(f"  On-Chain: {'✓ Habilitado' if self.get('data.include_onchain') else '✗ Deshabilitado'}")
        logger.info(f"  Sentiment: {'✓ Habilitado' if self.get('data.include_sentiment') else '✗ Deshabilitado'}")
        
        logger.info(f"\n🤖 MODELO:")
        logger.info(f"  Optuna Trials: {self.get('model.optuna_trials')}")
        logger.info(f"  Model Dir: {self.get('model.model_dir')}")
        
        logger.info(f"\n🔧 DESARROLLO:")
        logger.info(f"  Simulated Data: {self.get('dev.use_simulated_data')}")
        logger.info(f"  Paper Trading: {self.get('dev.paper_trading')}")
        
        logger.info("=" * 70 + "\n")


# Testing
if __name__ == "__main__":
    # Test 1: Cargar desde archivo
    config = ConfigLoader('config.yaml')
    config.print_summary()
    
    # Test 2: Acceder a valores
    print(f"\nCapital: ${config.get('risk.total_capital')}")
    print(f"Symbol: {config.get('exchange.symbol')}")
    print(f"Testnet: {config.get('exchange.testnet')}")
    
    # Test 3: Config de exchange
    exchange_config = config.get_exchange_config()
    print(f"\nExchange Config: {exchange_config}")
    
    # Test 4: API Keys
    api_keys = config.get_api_keys()
    print(f"\nAPI Keys disponibles: {list(api_keys.keys())}")