"""
Cache Manager - Sistema de Caché Inteligente
Guarda y carga datos para evitar descargas repetidas
"""

import os
import pickle
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CacheManager")


class CacheManager:
    """
    Gestor de caché para datos de mercado y features.

    Features:
    - Guarda datos descargados (OHLCV, sentiment, defillama, coinglass)
    - Actualiza incrementalmente (solo descarga datos nuevos)
    - Cachea features calculadas
    - Detecta automáticamente cuándo actualizar
    """

    def __init__(self, cache_dir: str = "./data/cache"):
        """
        Args:
            cache_dir: Directorio para guardar archivos de cache
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectorios
        self.data_cache_dir = self.cache_dir / "data"
        self.features_cache_dir = self.cache_dir / "features"

        self.data_cache_dir.mkdir(exist_ok=True)
        self.features_cache_dir.mkdir(exist_ok=True)

        logger.info(f"📦 CacheManager inicializado: {self.cache_dir}")

    def _get_cache_path(self, cache_type: str, key: str) -> Path:
        """
        Obtiene la ruta del archivo de cache.

        Args:
            cache_type: 'data' o 'features'
            key: Identificador único (ej: 'ETHUSDT_1h', 'sentiment', etc.)

        Returns:
            Path al archivo de cache
        """
        if cache_type == 'data':
            return self.data_cache_dir / f"{key}.pkl"
        elif cache_type == 'features':
            return self.features_cache_dir / f"{key}.pkl"
        else:
            raise ValueError(f"cache_type inválido: {cache_type}")

    def save_data(self, key: str, data: pd.DataFrame, metadata: Optional[Dict] = None):
        """
        Guarda un DataFrame en cache con metadata opcional.

        Args:
            key: Identificador único (ej: 'ETHUSDT_1h')
            data: DataFrame a guardar
            metadata: Información adicional (ej: última actualización)
        """
        try:
            cache_path = self._get_cache_path('data', key)

            # Preparar objeto de cache
            cache_obj = {
                'data': data,
                'metadata': metadata or {},
                'timestamp': datetime.now(),
                'version': '1.0'
            }

            # Guardar
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_obj, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(f"💾 Guardado en cache: {key} ({len(data)} registros)")

        except Exception as e:
            logger.error(f"❌ Error guardando cache {key}: {e}")

    def load_data(self, key: str, max_age_hours: Optional[float] = None) -> Optional[pd.DataFrame]:
        """
        Carga un DataFrame del cache.

        Args:
            key: Identificador único
            max_age_hours: Máxima edad del cache en horas (None = sin límite)

        Returns:
            DataFrame si existe y es válido, None si no
        """
        try:
            cache_path = self._get_cache_path('data', key)

            # Verificar si existe
            if not cache_path.exists():
                logger.debug(f"❌ Cache no existe: {key}")
                return None

            # Cargar
            with open(cache_path, 'rb') as f:
                cache_obj = pickle.load(f)

            # Verificar edad si se especificó max_age_hours
            if max_age_hours is not None:
                cache_age = datetime.now() - cache_obj['timestamp']
                if cache_age > timedelta(hours=max_age_hours):
                    logger.info(f"⏰ Cache expirado: {key} (edad: {cache_age.total_seconds()/3600:.1f}h)")
                    return None

            data = cache_obj['data']
            cache_age = datetime.now() - cache_obj['timestamp']

            logger.info(f"📂 Cargado de cache: {key} ({len(data)} registros, edad: {cache_age.total_seconds()/60:.0f} min)")

            return data

        except Exception as e:
            logger.warning(f"⚠️ Error cargando cache {key}: {e}")
            return None

    def get_last_timestamp(self, key: str) -> Optional[datetime]:
        """
        Obtiene el timestamp más reciente de los datos en cache.

        Args:
            key: Identificador único

        Returns:
            Último timestamp si existe, None si no
        """
        data = self.load_data(key)

        if data is None or data.empty:
            return None

        # Si el index es DatetimeIndex
        if isinstance(data.index, pd.DatetimeIndex):
            return data.index[-1].to_pydatetime()

        # Si hay una columna 'timestamp'
        if 'timestamp' in data.columns:
            return pd.to_datetime(data['timestamp']).max().to_pydatetime()

        return None

    def append_data(self, key: str, new_data: pd.DataFrame, dedup: bool = True):
        """
        Agrega nuevos datos al cache existente (update incremental).

        Args:
            key: Identificador único
            new_data: Nuevos datos a agregar
            dedup: Si True, elimina duplicados por index
        """
        try:
            # Cargar datos existentes
            existing_data = self.load_data(key)

            if existing_data is None or existing_data.empty:
                # No hay datos previos, guardar directamente
                self.save_data(key, new_data)
                return

            # Combinar
            combined = pd.concat([existing_data, new_data])

            # Eliminar duplicados si se especificó
            if dedup:
                if isinstance(combined.index, pd.DatetimeIndex):
                    # Eliminar duplicados por index
                    combined = combined[~combined.index.duplicated(keep='last')]
                else:
                    # Eliminar duplicados por todas las columnas
                    combined = combined.drop_duplicates(keep='last')

            # Ordenar por index
            combined = combined.sort_index()

            # Guardar
            self.save_data(key, combined)

            new_rows = len(combined) - len(existing_data)
            logger.info(f"➕ Agregados {new_rows} registros nuevos a {key}")

        except Exception as e:
            logger.error(f"❌ Error agregando datos a cache {key}: {e}")

    def save_features(self, key: str, features_df: pd.DataFrame, config: Optional[Dict] = None):
        """
        Guarda features calculadas en cache.

        Args:
            key: Identificador único (ej: 'features_1h_96')
            features_df: DataFrame con features
            config: Configuración usada para generar features
        """
        metadata = {
            'config': config,
            'n_features': len(features_df.columns),
            'n_samples': len(features_df)
        }

        self.save_data(key, features_df, metadata)

    def load_features(self, key: str, max_age_hours: float = 24) -> Optional[pd.DataFrame]:
        """
        Carga features del cache.

        Args:
            key: Identificador único
            max_age_hours: Máxima edad del cache (default: 24h)

        Returns:
            DataFrame de features o None
        """
        return self.load_data(key, max_age_hours=max_age_hours)

    def clear_cache(self, cache_type: Optional[str] = None):
        """
        Limpia el cache.

        Args:
            cache_type: 'data', 'features', o None (ambos)
        """
        try:
            if cache_type in ['data', None]:
                for f in self.data_cache_dir.glob('*.pkl'):
                    f.unlink()
                logger.info("🗑️ Cache de datos limpiado")

            if cache_type in ['features', None]:
                for f in self.features_cache_dir.glob('*.pkl'):
                    f.unlink()
                logger.info("🗑️ Cache de features limpiado")

        except Exception as e:
            logger.error(f"❌ Error limpiando cache: {e}")

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre el estado del cache.

        Returns:
            Diccionario con estadísticas del cache
        """
        info = {
            'data_cache': {},
            'features_cache': {},
            'total_size_mb': 0.0
        }

        # Cache de datos
        for f in self.data_cache_dir.glob('*.pkl'):
            size_mb = f.stat().st_size / (1024 * 1024)
            age_hours = (datetime.now().timestamp() - f.stat().st_mtime) / 3600

            info['data_cache'][f.stem] = {
                'size_mb': round(size_mb, 2),
                'age_hours': round(age_hours, 1)
            }
            info['total_size_mb'] += size_mb

        # Cache de features
        for f in self.features_cache_dir.glob('*.pkl'):
            size_mb = f.stat().st_size / (1024 * 1024)
            age_hours = (datetime.now().timestamp() - f.stat().st_mtime) / 3600

            info['features_cache'][f.stem] = {
                'size_mb': round(size_mb, 2),
                'age_hours': round(age_hours, 1)
            }
            info['total_size_mb'] += size_mb

        info['total_size_mb'] = round(info['total_size_mb'], 2)

        return info

    def print_cache_info(self):
        """
        Muestra información del cache en consola.
        """
        info = self.get_cache_info()

        print("\n" + "="*60)
        print("📦 INFORMACIÓN DEL CACHE")
        print("="*60)

        print("\n📊 DATA CACHE:")
        if info['data_cache']:
            for key, stats in info['data_cache'].items():
                print(f"  • {key}: {stats['size_mb']} MB (edad: {stats['age_hours']:.1f}h)")
        else:
            print("  (vacío)")

        print("\n🔬 FEATURES CACHE:")
        if info['features_cache']:
            for key, stats in info['features_cache'].items():
                print(f"  • {key}: {stats['size_mb']} MB (edad: {stats['age_hours']:.1f}h)")
        else:
            print("  (vacío)")

        print(f"\n💾 TAMAÑO TOTAL: {info['total_size_mb']} MB")
        print("="*60 + "\n")


# --- EJEMPLO DE USO ---
if __name__ == "__main__":
    # Crear cache manager
    cache = CacheManager()

    # Simular datos
    import numpy as np
    dates = pd.date_range('2024-01-01', periods=1000, freq='1h')
    df = pd.DataFrame({
        'open': np.random.randn(1000) + 2000,
        'high': np.random.randn(1000) + 2010,
        'low': np.random.randn(1000) + 1990,
        'close': np.random.randn(1000) + 2000,
        'volume': np.random.randn(1000) * 1000 + 10000
    }, index=dates)

    # Guardar
    print("💾 Guardando datos en cache...")
    cache.save_data('ETHUSDT_1h', df)

    # Cargar
    print("\n📂 Cargando datos del cache...")
    loaded = cache.load_data('ETHUSDT_1h')
    print(f"✓ Cargado: {len(loaded)} registros")

    # Agregar más datos
    print("\n➕ Agregando datos nuevos...")
    new_dates = pd.date_range('2024-02-11', periods=100, freq='1h')
    new_df = pd.DataFrame({
        'open': np.random.randn(100) + 2000,
        'high': np.random.randn(100) + 2010,
        'low': np.random.randn(100) + 1990,
        'close': np.random.randn(100) + 2000,
        'volume': np.random.randn(100) * 1000 + 10000
    }, index=new_dates)

    cache.append_data('ETHUSDT_1h', new_df)

    # Info del cache
    cache.print_cache_info()

    print("✅ Test completado!")
