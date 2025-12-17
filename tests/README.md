# Test Suite

Comprehensive testing for ETH trading system feature engineering.

## Test Modules

### 1. `test_feature_engineering.py`
Tests for core feature engineering pipeline.

**Coverage:**
- Technical indicators (RSI, ATR, volatility)
- Phase 3 statistical features (skewness, kurtosis, autocorrelation)
- Phase 4 tsfresh-inspired features (entropy, Benford correlation)
- Macro feature integration
- Edge cases (empty data, insufficient data)
- Data quality (no infinite values, no NaN)

**Run:**
```bash
pytest tests/test_feature_engineering.py -v
```

### 2. `test_tsfresh.py`
Tests for automated feature extraction (FASE 5).

**Coverage:**
- TSFreshEngine: data preparation, extraction, selection, caching
- FeatureSelector: significance testing, FDR correction, redundancy removal
- Convenience functions: `get_tsfresh_features()`, `select_features()`
- Statistical validation (Benjamini-Hochberg, correlation tests)

**Run:**
```bash
pytest tests/test_tsfresh.py -v
```

### 3. `test_model_performance.py`
Integration tests and performance benchmarks.

**Coverage:**
- Full pipeline execution
- Feature count validation (100+ features)
- Feature quality checks (no infinite, no NaN, variance)
- Feature correlation with target
- Train/test split stability
- Performance benchmarking (speed, memory)
- Phase verification (1-6)

**Run:**
```bash
pytest tests/test_model_performance.py -v -s
```

## Running All Tests

### Run all tests
```bash
pytest tests/ -v
```

### Run with coverage
```bash
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

### Run specific test class
```bash
pytest tests/test_feature_engineering.py::TestFeatureEngineer -v
```

### Run specific test
```bash
pytest tests/test_feature_engineering.py::TestFeatureEngineer::test_create_technical_features -v
```

## Requirements

Install test dependencies:
```bash
pip install pytest pytest-cov
```

For tsfresh tests (optional):
```bash
pip install tsfresh
```

## Expected Results

All tests should pass with the complete implementation:

```
tests/test_feature_engineering.py ............... PASSED [XX%]
tests/test_tsfresh.py ........................... PASSED [XX%]
tests/test_model_performance.py ................. PASSED [XX%]

======================== XX passed in X.XXs ========================
```

## Test Data

Tests use synthetic data generated with:
- Realistic price movements (random walk with drift)
- Volume (log-normal distribution)
- Various time series (OBI, VPIN, funding rates)

## Continuous Integration

To integrate with CI/CD:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest tests/ -v --cov
```

## Performance Benchmarks

Expected performance on typical hardware:

| Dataset Size | Features | Time | Speed |
|--------------|----------|------|-------|
| 200 rows     | 100+     | <2s  | >100 rows/s |
| 500 rows     | 100+     | <5s  | >100 rows/s |
| 1000 rows    | 100+     | <15s | >60 rows/s |

## Feature Count Targets

| Phase | Features | Status |
|-------|----------|--------|
| FASE 1 | 49       | ✅ Complete |
| FASE 2 | 18       | ✅ Complete |
| FASE 3 | 57       | ✅ Complete |
| FASE 4 | 100      | ✅ Complete |
| FASE 5 | 100      | ✅ Complete |
| **Total** | **324+** | **✅ Target Met** |

## Troubleshooting

### tsfresh tests skipped
- Install tsfresh: `pip install tsfresh`
- Tests will auto-skip if tsfresh not available

### Tests timing out
- Reduce dataset size in fixtures
- Use `pytest -v --timeout=30` to set timeout

### Import errors
- Ensure all feature modules are installed
- Check that QuestDB connection is available for microstructure tests

## Contributing

When adding new features:
1. Add tests to appropriate test module
2. Ensure all tests pass
3. Update this README with new coverage
4. Run performance benchmarks
