"""
Model Loader
Carga y gestiona metadata de modelos entrenados
"""

import json
import pickle
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ModelLoader:
    """Carga y gestiona modelos XGBoost"""

    def __init__(self, models_dir='models'):
        self.models_dir = Path(models_dir)

    def list_models(self):
        """
        Lista todos los modelos disponibles

        Returns:
            List[dict]: Lista de modelos con metadata
        """
        if not self.models_dir.exists():
            return []

        models = []

        for model_file in self.models_dir.glob('model_*.json'):
            try:
                # Extraer símbolo del nombre
                symbol = model_file.stem.replace('model_', '')

                # Cargar metadata si existe
                metadata_file = self.models_dir / f'{model_file.stem}_metadata.pkl'
                metadata = {}

                if metadata_file.exists():
                    with open(metadata_file, 'rb') as f:
                        metadata = pickle.load(f)

                # Info del archivo
                stat = model_file.stat()
                last_modified = datetime.fromtimestamp(stat.st_mtime)

                models.append({
                    'symbol': symbol,
                    'model_file': str(model_file),
                    'metadata_file': str(metadata_file) if metadata_file.exists() else None,
                    'last_trained': last_modified,
                    'size_mb': stat.st_size / (1024 * 1024),
                    'metadata': metadata
                })

            except Exception as e:
                logger.error(f"Error cargando modelo {model_file}: {e}")
                continue

        # Ordenar por fecha (más reciente primero)
        models.sort(key=lambda x: x['last_trained'], reverse=True)

        return models

    def get_model_metadata(self, symbol):
        """
        Obtiene metadata de un modelo específico

        Args:
            symbol: Símbolo del par (ej: 'ETHUSDT')

        Returns:
            dict: Metadata del modelo o None
        """
        metadata_file = self.models_dir / f'model_{symbol}_metadata.pkl'

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"Error cargando metadata de {symbol}: {e}")
            return None

    def get_training_summary(self):
        """
        Obtiene resumen de todos los entrenamientos

        Returns:
            dict: Resumen con estadísticas
        """
        models = self.list_models()

        if not models:
            return {
                'total_models': 0,
                'avg_accuracy': 0,
                'best_model': None,
                'worst_model': None,
                'last_training': None
            }

        accuracies = []
        for model in models:
            meta = model.get('metadata', {})
            if 'test_accuracy' in meta:
                accuracies.append({
                    'symbol': model['symbol'],
                    'accuracy': meta['test_accuracy']
                })

        best_model = max(accuracies, key=lambda x: x['accuracy']) if accuracies else None
        worst_model = min(accuracies, key=lambda x: x['accuracy']) if accuracies else None
        avg_accuracy = sum(m['accuracy'] for m in accuracies) / len(accuracies) if accuracies else 0

        return {
            'total_models': len(models),
            'avg_accuracy': avg_accuracy,
            'best_model': best_model,
            'worst_model': worst_model,
            'last_training': models[0]['last_trained'] if models else None,
            'models': models
        }
