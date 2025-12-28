"""
Script para generar archivos de metadata a partir de resultados de entrenamiento
Ejecutar: python generate_metadata_from_results.py
"""

import json
from pathlib import Path

# Datos extraídos de los logs de entrenamiento
TRAINING_RESULTS = {
    'ETHUSDT': {
        'accuracy': 0.69,
        'precision_short': 0.72,
        'precision_long': 0.64,
        'recall_short': 0.74,
        'recall_long': 0.62,
        'f1_short': 0.73,
        'f1_long': 0.63,
        'support_short': 103,
        'support_long': 78,
        'test_samples': 181,
        'train_samples': 903 - 181  # Total - test
    },
    'SOLUSDT': {
        'accuracy': 0.60,
        'precision_short': 0.57,
        'precision_long': 0.63,
        'recall_short': 0.56,
        'recall_long': 0.64,
        'f1_short': 0.56,
        'f1_long': 0.64,
        'support_short': 171,
        'support_long': 199,
        'test_samples': 370,
        'train_samples': 1848 - 370
    },
    'BNBUSDT': {
        'accuracy': 0.52,
        'precision_short': 0.57,
        'precision_long': 0.50,
        'recall_short': 0.40,
        'recall_long': 0.66,
        'f1_short': 0.47,
        'f1_long': 0.57,
        'support_short': 97,
        'support_long': 86,
        'test_samples': 183,
        'train_samples': 912 - 183
    },
    'XRPUSDT': {
        'accuracy': 0.50,
        'precision_short': 0.30,
        'precision_long': 0.70,
        'recall_short': 0.49,
        'recall_long': 0.50,
        'f1_short': 0.37,
        'f1_long': 0.59,
        'support_short': 51,
        'support_long': 119,
        'test_samples': 170,
        'train_samples': 846 - 170
    },
    'ADAUSDT': {
        'accuracy': 0.56,
        'precision_short': 0.66,
        'precision_long': 0.55,
        'recall_short': 0.16,
        'recall_long': 0.92,
        'f1_short': 0.26,
        'f1_long': 0.69,
        'support_short': 128,
        'support_long': 143,
        'test_samples': 271,
        'train_samples': 1355 - 271
    },
    'DOGEUSDT': {
        'accuracy': 0.54,
        'precision_short': 0.53,
        'precision_long': 0.55,
        'recall_short': 0.50,
        'recall_long': 0.59,
        'f1_short': 0.51,
        'f1_long': 0.57,
        'support_short': 165,
        'support_long': 176,
        'test_samples': 341,
        'train_samples': 1705 - 341
    },
    'DOTUSDT': {
        'accuracy': 0.45,
        'precision_short': 0.50,
        'precision_long': 0.45,
        'recall_short': 0.02,
        'recall_long': 0.98,
        'f1_short': 0.04,
        'f1_long': 0.62,
        'support_short': 159,
        'support_long': 131,
        'test_samples': 290,
        'train_samples': 1450 - 290
    },
    'LINKUSDT': {
        'accuracy': 0.74,
        'precision_short': 0.83,
        'precision_long': 0.68,
        'recall_short': 0.64,
        'recall_long': 0.85,
        'f1_short': 0.72,
        'f1_long': 0.76,
        'support_short': 151,
        'support_long': 135,
        'test_samples': 286,
        'train_samples': 1429 - 286
    },
    'UNIUSDT': {
        'accuracy': 0.55,
        'precision_short': 0.58,
        'precision_long': 0.50,
        'recall_short': 0.69,
        'recall_long': 0.38,
        'f1_short': 0.63,
        'f1_long': 0.43,
        'support_short': 191,
        'support_long': 157,
        'test_samples': 348,
        'train_samples': 1736 - 348
    },
    'ATOMUSDT': {
        'accuracy': 0.51,
        'precision_short': 0.55,
        'precision_long': 0.48,
        'recall_short': 0.48,
        'recall_long': 0.55,
        'f1_short': 0.51,
        'f1_long': 0.51,
        'support_short': 127,
        'support_long': 111,
        'test_samples': 238,
        'train_samples': 1186 - 238
    },
    'AVAXUSDT': {
        'accuracy': 0.50,
        'precision_short': 0.68,
        'precision_long': 0.48,
        'recall_short': 0.13,
        'recall_long': 0.93,
        'f1_short': 0.22,
        'f1_long': 0.63,
        'support_short': 200,
        'support_long': 172,
        'test_samples': 372,
        'train_samples': 1856 - 372
    },
    'LTCUSDT': {
        'accuracy': 0.56,
        'precision_short': 0.74,
        'precision_long': 0.47,
        'recall_short': 0.39,
        'recall_long': 0.80,
        'f1_short': 0.51,
        'f1_long': 0.60,
        'support_short': 116,
        'support_long': 80,
        'test_samples': 196,
        'train_samples': 978 - 196
    },
    'ETCUSDT': {
        'accuracy': 0.50,
        'precision_short': 0.56,
        'precision_long': 0.48,
        'recall_short': 0.30,
        'recall_long': 0.73,
        'f1_short': 0.39,
        'f1_long': 0.58,
        'support_short': 153,
        'support_long': 135,
        'test_samples': 288,
        'train_samples': 1437 - 288
    },
    'FILUSDT': {
        'accuracy': 0.58,
        'precision_short': 0.73,
        'precision_long': 0.50,
        'recall_short': 0.44,
        'recall_long': 0.77,
        'f1_short': 0.54,
        'f1_long': 0.61,
        'support_short': 218,
        'support_long': 158,
        'test_samples': 376,
        'train_samples': 1878 - 376
    },
    'APTUSDT': {
        'accuracy': 0.56,
        'precision_short': 0.71,
        'precision_long': 0.52,
        'recall_short': 0.29,
        'recall_long': 0.86,
        'f1_short': 0.41,
        'f1_long': 0.65,
        'support_short': 191,
        'support_long': 168,
        'test_samples': 359,
        'train_samples': 1792 - 359
    },
    'ARBUSDT': {
        'accuracy': 0.48,
        'precision_short': 0.55,
        'precision_long': 0.46,
        'recall_short': 0.25,
        'recall_long': 0.75,
        'f1_short': 0.34,
        'f1_long': 0.57,
        'support_short': 191,
        'support_long': 162,
        'test_samples': 353,
        'train_samples': 1764 - 353
    },
    'OPUSDT': {
        'accuracy': 0.48,
        'precision_short': 0.48,
        'precision_long': 0.49,
        'recall_short': 0.42,
        'recall_long': 0.55,
        'f1_short': 0.45,
        'f1_long': 0.52,
        'support_short': 199,
        'support_long': 199,
        'test_samples': 398,
        'train_samples': 1986 - 398
    },
    'INJUSDT': {
        'accuracy': 0.59,
        'precision_short': 0.81,
        'precision_long': 0.53,
        'recall_short': 0.31,
        'recall_long': 0.92,
        'f1_short': 0.45,
        'f1_long': 0.67,
        'support_short': 246,
        'support_long': 212,
        'test_samples': 458,
        'train_samples': 2287 - 458
    },
    'SUIUSDT': {
        'accuracy': 0.46,
        'precision_short': 0.48,
        'precision_long': 0.45,
        'recall_short': 0.32,
        'recall_long': 0.61,
        'f1_short': 0.38,
        'f1_long': 0.52,
        'support_short': 240,
        'support_long': 217,
        'test_samples': 457,
        'train_samples': 2284 - 457
    }
}


def main():
    """Genera archivos de metadata para todos los modelos"""

    models_dir = Path('models')
    models_dir.mkdir(exist_ok=True)

    print("📝 Generando archivos de metadata...")
    print("=" * 60)

    for symbol, metrics in TRAINING_RESULTS.items():
        metadata_file = models_dir / f'model_{symbol}_metadata.json'

        with open(metadata_file, 'w') as f:
            json.dump(metrics, f, indent=2)

        print(f"✓ {symbol}: accuracy={metrics['accuracy']:.2%}, samples={metrics['test_samples']}")

    print("=" * 60)
    print(f"✅ Generados {len(TRAINING_RESULTS)} archivos de metadata en {models_dir}/")
    print("\nAhora puedes ejecutar el dashboard y verás las métricas correctas:")
    print("  python -m streamlit run web_dashboard.py")


if __name__ == '__main__':
    main()
