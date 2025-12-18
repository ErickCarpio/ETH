"""
Quick test of statistical features implementation
"""
import numpy as np
import pandas as pd
import sys

print("🧪 Testing Statistical Features Implementation...")
print("=" * 60)

# Test 1: Import test
print("\n1️⃣ Testing imports...")
try:
    from features.statistical.statistical_features import StatisticalFeatureEngine
    print("   ✅ StatisticalFeatureEngine imported successfully")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Initialization test
print("\n2️⃣ Testing initialization...")
try:
    config = {
        'hurst_windows': [24, 72, 168],
        'kalman_initial_estimate': 0.01,
        'wavelet_scales': [1, 2, 4, 8, 16, 32, 64, 128],
        'fft_n_coefs': 20
    }
    engine = StatisticalFeatureEngine(config)
    print("   ✅ Engine initialized successfully")
except Exception as e:
    print(f"   ❌ Initialization failed: {e}")
    sys.exit(1)

# Test 3: Feature generation test
print("\n3️⃣ Testing feature generation on sample data...")
try:
    # Generate sample price data
    np.random.seed(42)
    n = 300
    t = np.linspace(0, 10, n)

    # Realistic ETH price simulation
    trend = 0.5 * t
    cycle = 100 * np.sin(2 * np.pi * t / 5)
    noise = np.random.randn(n) * 20
    prices = trend + cycle + noise + 2000

    df_test = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'close': prices
    })
    df_test.set_index('timestamp', inplace=True)

    print(f"   📊 Generated {len(df_test)} rows of sample data")
    print(f"   💰 Price range: ${df_test['close'].min():.2f} - ${df_test['close'].max():.2f}")

    # Calculate features
    df_result = engine.compute_all_features(df_test, price_col='close')

    # Count statistical features
    statistical_cols = [col for col in df_result.columns if any(
        keyword in col for keyword in [
            'hurst', 'kalman', 'wavelet', 'fft', 'entropy', 'fractal',
            'skewness', 'kurtosis', 'autocorr', 'dfa'
        ]
    )]

    print(f"\n   ✅ Features generated successfully!")
    print(f"   📈 Total statistical features: {len(statistical_cols)}")
    print(f"   📋 Total columns: {len(df_result.columns)}")

except Exception as e:
    print(f"   ❌ Feature generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Show feature categories
print("\n4️⃣ Feature categories breakdown:")
categories = {
    'Hurst': [c for c in statistical_cols if 'hurst' in c],
    'Kalman': [c for c in statistical_cols if 'kalman' in c],
    'Wavelet': [c for c in statistical_cols if 'wavelet' in c],
    'FFT': [c for c in statistical_cols if 'fft' in c],
    'Entropy': [c for c in statistical_cols if 'entropy' in c],
    'Fractal': [c for c in statistical_cols if 'fractal' in c],
    'Skewness': [c for c in statistical_cols if 'skewness' in c],
    'Kurtosis': [c for c in statistical_cols if 'kurtosis' in c],
    'Autocorr': [c for c in statistical_cols if 'autocorr' in c],
    'DFA': [c for c in statistical_cols if 'dfa' in c],
}

for category, features in categories.items():
    if features:
        print(f"   🔹 {category}: {len(features)} features")
        print(f"      Examples: {', '.join(features[:3])}")

# Test 5: Sample values
print("\n5️⃣ Sample feature values (last row):")
sample_features = statistical_cols[:5]
for feat in sample_features:
    value = df_result[feat].iloc[-1]
    print(f"   {feat}: {value:.6f}")

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print(f"📊 Statistical Feature Engine is ready with {len(statistical_cols)} features")
