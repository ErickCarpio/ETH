"""
Training Panel
Panel para entrenar modelos (Full/Weekly/Daily)
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.subprocess_runner import SubprocessRunner
from utils.model_loader import ModelLoader


def render_training_panel():
    """Renderiza el panel de entrenamiento"""

    st.header("🧠 Entrenamiento de Modelos")

    # Selector de modo
    st.subheader("Tipo de Entrenamiento")

    training_mode = st.radio(
        "Selecciona el modo:",
        [
            "Full Training (20 pares, 1000 trials, 730 días)",
            "Weekly Calibration (1 par, 100 trials, 90 días)",
            "Daily Refresh (1 par, 0 trials, 30 días)"
        ],
        key="training_mode"
    )

    st.markdown("---")

    # Configuración según modo
    if "Full Training" in training_mode:
        render_full_training()
    elif "Weekly Calibration" in training_mode:
        render_weekly_calibration()
    else:
        render_daily_refresh()

    st.markdown("---")

    # Panel de resultados
    render_training_results()


def render_full_training():
    """Renderiza interfaz de Full Training"""

    st.subheader("⚙️ Configuración Full Training")

    # Lista de pares disponibles
    all_pairs = [
        'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
        'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT',
        'ATOMUSDT', 'AVAXUSDT', 'LTCUSDT', 'ETCUSDT', 'FILUSDT',
        'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT'
    ]

    col1, col2 = st.columns(2)

    with col1:
        # Selector rápido
        quick_select = st.selectbox(
            "Selección rápida:",
            ["Personalizado", "Top 5", "Top 10", "Todos (20)"]
        )

        if quick_select == "Top 5":
            selected_pairs = all_pairs[:5]
        elif quick_select == "Top 10":
            selected_pairs = all_pairs[:10]
        elif quick_select == "Todos (20)":
            selected_pairs = all_pairs
        else:
            selected_pairs = st.session_state.get('selected_pairs', all_pairs[:5])

    with col2:
        st.info(f"📊 {len(selected_pairs)} pares seleccionados")

    # Multi-select manual
    if quick_select == "Personalizado":
        selected_pairs = st.multiselect(
            "Selecciona pares:",
            all_pairs,
            default=st.session_state.get('selected_pairs', all_pairs[:5])
        )
        st.session_state['selected_pairs'] = selected_pairs

    # Parámetros
    col1, col2 = st.columns(2)

    with col1:
        days = st.slider("Días históricos:", 365, 1000, 730, step=30)

    with col2:
        trials = st.slider("Optuna trials:", 100, 2000, 1000, step=100)

    # Botón de entrenamiento
    if st.button("🚀 Entrenar Modelos", type="primary", disabled=len(selected_pairs) == 0):
        start_full_training(selected_pairs, days, trials)


def render_weekly_calibration():
    """Renderiza interfaz de Weekly Calibration"""

    st.subheader("⚙️ Configuración Weekly Calibration")

    # Selector de modelo loader
    model_loader = ModelLoader()
    models = model_loader.list_models()

    if not models:
        st.warning("⚠️ No hay modelos entrenados. Ejecuta Full Training primero.")
        return

    # Selector de par
    symbols = [m['symbol'] for m in models]
    selected_symbol = st.selectbox("Selecciona par a calibrar:", symbols)

    # Info del modelo actual
    if selected_symbol:
        model_meta = model_loader.get_model_metadata(selected_symbol)
        if model_meta:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Accuracy Actual", f"{model_meta.get('test_accuracy', 0) * 100:.1f}%")
            with col2:
                st.metric("F1-Score", f"{model_meta.get('test_f1', 0):.3f}")
            with col3:
                last_trained = next((m['last_trained'] for m in models if m['symbol'] == selected_symbol), None)
                if last_trained:
                    st.metric("Última actualización", last_trained.strftime('%Y-%m-%d'))

    st.info("📊 Weekly Calibration: 100 trials, 90 días de datos")

    # Botón
    if st.button("🔄 Calibrar Modelo", type="primary"):
        start_weekly_calibration(selected_symbol)


def render_daily_refresh():
    """Renderiza interfaz de Daily Refresh"""

    st.subheader("⚙️ Configuración Daily Refresh")

    # Selector de modelo
    model_loader = ModelLoader()
    models = model_loader.list_models()

    if not models:
        st.warning("⚠️ No hay modelos entrenados. Ejecuta Full Training primero.")
        return

    # Selector de par
    symbols = [m['symbol'] for m in models]
    selected_symbol = st.selectbox("Selecciona par a actualizar:", symbols)

    st.info("⚡ Daily Refresh: 0 trials (usa mejores params), 30 días de datos")
    st.warning("💡 Rápido (~2-5 min) - Solo actualiza con datos recientes")

    # Botón
    if st.button("⚡ Actualizar Modelo", type="primary"):
        start_daily_refresh(selected_symbol)


def start_full_training(pairs, days, trials):
    """Inicia Full Training"""

    st.session_state['training_running'] = True
    st.session_state['training_logs'] = []

    # Crear archivo temporal con lista de pares
    pairs_str = ','.join(pairs)

    # Ejecutar script
    with st.spinner(f"Entrenando {len(pairs)} modelos..."):
        st.info(f"📊 Entrenando: {pairs_str}")
        st.info(f"⚙️ Configuración: {days} días, {trials} trials por modelo")

        # TODO: Ejecutar train_multiple_pairs.py en subprocess
        # Por ahora, mostrar instrucciones
        st.code(f"""
# Ejecuta este comando en terminal:
python train_multiple_pairs.py --pairs {len(pairs)} --days {days} --trials {trials}

# O espera a que se implemente subprocess runner
        """, language="bash")

        st.session_state['training_running'] = False


def start_weekly_calibration(symbol):
    """Inicia Weekly Calibration"""
    st.info(f"🔄 Calibrando {symbol}...")
    st.code(f"""
# Ejecuta este comando en terminal:
python train_multiple_pairs.py --pair {symbol} --days 90 --trials 100 --warmstart

# O espera a que se implemente subprocess runner
    """, language="bash")


def start_daily_refresh(symbol):
    """Inicia Daily Refresh"""
    st.info(f"⚡ Actualizando {symbol}...")
    st.code(f"""
# Ejecuta este comando en terminal:
python train_multiple_pairs.py --pair {symbol} --days 30 --trials 0 --warmstart

# O espera a que se implemente subprocess runner
    """, language="bash")


def render_training_results():
    """Renderiza resultados de entrenamientos"""

    st.subheader("📊 Modelos Entrenados")

    model_loader = ModelLoader()
    summary = model_loader.get_training_summary()

    if summary['total_models'] == 0:
        st.info("ℹ️ No hay modelos entrenados aún.")
        return

    # Métricas generales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Modelos", summary['total_models'])

    with col2:
        st.metric("Accuracy Promedio", f"{summary['avg_accuracy'] * 100:.1f}%")

    with col3:
        if summary['best_model']:
            st.metric(
                "Mejor Modelo",
                summary['best_model']['symbol'],
                f"{summary['best_model']['accuracy'] * 100:.1f}%"
            )

    with col4:
        if summary['last_training']:
            st.metric("Último Entrenamiento", summary['last_training'].strftime('%Y-%m-%d'))

    # Tabla de modelos
    st.markdown("### 📋 Lista de Modelos")

    models = summary['models']

    import pandas as pd

    df_models = pd.DataFrame([
        {
            'Symbol': m['symbol'],
            'Accuracy': f"{m['metadata'].get('test_accuracy', 0) * 100:.1f}%",
            'F1-Score': f"{m['metadata'].get('test_f1', 0):.3f}",
            'Samples': m['metadata'].get('train_samples', 0),
            'Last Trained': m['last_trained'].strftime('%Y-%m-%d %H:%M')
        }
        for m in models
    ])

    st.dataframe(df_models, use_container_width=True, height=400)
