"""
Models Panel
Panel para monitorear y gestionar modelos
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
import plotly.graph_objects as go

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.model_loader import ModelLoader


def render_models_panel():
    """Renderiza el panel de modelos"""

    st.header("🔧 Gestión de Modelos")

    model_loader = ModelLoader()
    models = model_loader.list_models()

    if not models:
        st.warning("⚠️ No hay modelos entrenados. Ve a la pestaña Training para entrenar modelos.")
        return

    # Panel de resumen
    render_models_summary(model_loader)

    st.markdown("---")

    # Tabla de modelos
    render_models_table(models, model_loader)

    st.markdown("---")

    # Comparación de modelos
    render_models_comparison(models)


def render_models_summary(model_loader):
    """Renderiza resumen de modelos"""

    summary = model_loader.get_training_summary()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📊 Total Modelos", summary['total_models'])

    with col2:
        st.metric("📈 Accuracy Promedio", f"{summary['avg_accuracy'] * 100:.1f}%")

    with col3:
        if summary['best_model']:
            st.metric(
                "🏆 Mejor Modelo",
                summary['best_model']['symbol'],
                f"{summary['best_model']['accuracy'] * 100:.1f}%"
            )

    with col4:
        if summary['last_training']:
            hours_ago = (pd.Timestamp.now() - pd.Timestamp(summary['last_training'])).total_seconds() / 3600
            if hours_ago < 24:
                time_str = f"{int(hours_ago)}h ago"
            else:
                time_str = f"{int(hours_ago / 24)}d ago"

            st.metric("🕐 Último Training", time_str)


def render_models_table(models, model_loader):
    """Renderiza tabla de modelos con acciones"""

    st.subheader("📋 Lista de Modelos")

    # Preparar datos para tabla
    table_data = []

    for model in models:
        meta = model.get('metadata', {})

        # Calcular edad
        hours_ago = (pd.Timestamp.now() - pd.Timestamp(model['last_trained'])).total_seconds() / 3600
        if hours_ago < 24:
            age_str = f"{int(hours_ago)}h"
        else:
            age_str = f"{int(hours_ago / 24)}d"

        # Buscar accuracy en diferentes formatos
        accuracy = meta.get('test_accuracy') or meta.get('accuracy') or meta.get('best_accuracy') or 0
        f1_score = meta.get('test_f1') or meta.get('f1') or meta.get('f1_score') or 0

        table_data.append({
            'Symbol': model['symbol'],
            'Accuracy': f"{accuracy * 100:.1f}%" if accuracy else "N/A",
            'F1-Score': f"{f1_score:.3f}" if f1_score else "N/A",
            'Trees': model.get('n_trees', 0),
            'Size (MB)': f"{model['size_mb']:.2f}",
            'Samples': meta.get('train_samples') or meta.get('samples', 0),
            'Age': age_str
        })

    df = pd.DataFrame(table_data)

    # Mostrar tabla
    st.dataframe(df, use_container_width=True, height=400)

    # Selector de modelo para detalles
    st.markdown("---")
    st.subheader("🔍 Detalles de Modelo")

    selected_symbol = st.selectbox(
        "Selecciona un modelo para ver detalles:",
        [m['symbol'] for m in models]
    )

    if selected_symbol:
        render_model_details(selected_symbol, model_loader)


def render_model_details(symbol, model_loader):
    """Renderiza detalles de un modelo específico"""

    meta = model_loader.get_model_metadata(symbol)

    if not meta:
        st.warning(f"⚠️ No hay metadata para {symbol}")
        return

    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Accuracy", f"{meta.get('test_accuracy', 0) * 100:.1f}%")

    with col2:
        st.metric("F1-Score", f"{meta.get('test_f1', 0):.3f}")

    with col3:
        st.metric("Precision (LONG)", f"{meta.get('precision_long', 0) * 100:.1f}%")

    with col4:
        st.metric("Recall (LONG)", f"{meta.get('recall_long', 0) * 100:.1f}%")

    # Hiperparámetros
    st.markdown("### 🔧 Hiperparámetros")

    best_params = meta.get('best_params', {})

    if best_params:
        col1, col2 = st.columns(2)

        with col1:
            for i, (key, value) in enumerate(list(best_params.items())[:len(best_params)//2]):
                if isinstance(value, float):
                    st.text(f"• {key}: {value:.4f}")
                else:
                    st.text(f"• {key}: {value}")

        with col2:
            for i, (key, value) in enumerate(list(best_params.items())[len(best_params)//2:]):
                if isinstance(value, float):
                    st.text(f"• {key}: {value:.4f}")
                else:
                    st.text(f"• {key}: {value}")

    # Feature importance (si existe)
    if 'feature_importance' in meta:
        st.markdown("### 📊 Features Más Importantes (Top 10)")

        feat_imp = meta['feature_importance']

        # Ordenar por importancia
        sorted_features = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:10]

        # Crear gráfico
        fig = go.Figure(data=[
            go.Bar(
                x=[f[1] for f in sorted_features],
                y=[f[0] for f in sorted_features],
                orientation='h',
                marker=dict(color='#3498db')
            )
        ])

        fig.update_layout(
            title="Feature Importance",
            xaxis_title="Importancia (%)",
            yaxis_title="Feature",
            height=400,
            yaxis={'categoryorder': 'total ascending'}
        )

        st.plotly_chart(fig, use_container_width=True)

    # Acciones
    st.markdown("### ⚡ Acciones")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 Re-entrenar Modelo", key=f"retrain_{symbol}"):
            st.info(f"🔄 Re-entrenando {symbol}...")
            st.code(f"""
# Ejecuta en terminal:
python train_multiple_pairs.py --pair {symbol} --warmstart
            """, language="bash")

    with col2:
        if st.button("📊 Hacer Backtest", key=f"backtest_{symbol}"):
            st.info("📊 Ve a la pestaña Backtest para ejecutar backtests")

    with col3:
        if st.button("🗑️ Eliminar Modelo", key=f"delete_{symbol}", type="secondary"):
            st.warning("⚠️ Esta acción es irreversible")
            confirm = st.checkbox(f"Confirmar eliminación de {symbol}")

            if confirm:
                if st.button("❌ Eliminar Definitivamente", type="primary"):
                    delete_model(symbol)


def delete_model(symbol):
    """Elimina un modelo"""
    models_dir = Path('models')

    model_file = models_dir / f'model_{symbol}.json'
    metadata_file = models_dir / f'model_{symbol}_metadata.pkl'

    try:
        if model_file.exists():
            model_file.unlink()
        if metadata_file.exists():
            metadata_file.unlink()

        st.success(f"✅ Modelo {symbol} eliminado")
        st.rerun()

    except Exception as e:
        st.error(f"❌ Error eliminando modelo: {e}")


def render_models_comparison(models):
    """Renderiza comparación de modelos"""

    st.subheader("📊 Comparación de Modelos")

    # Selector de modelos
    selected_models = st.multiselect(
        "Selecciona 2-5 modelos para comparar:",
        [m['symbol'] for m in models],
        default=[m['symbol'] for m in models[:min(3, len(models))]]
    )

    if len(selected_models) < 2:
        st.info("ℹ️ Selecciona al menos 2 modelos para comparar")
        return

    # Preparar datos
    comparison_data = []

    for symbol in selected_models:
        model = next((m for m in models if m['symbol'] == symbol), None)
        if model:
            meta = model.get('metadata', {})
            comparison_data.append({
                'Symbol': symbol,
                'Accuracy': meta.get('test_accuracy', 0) * 100,
                'F1-Score': meta.get('test_f1', 0) * 100,
                'Samples': meta.get('train_samples', 0)
            })

    df_comp = pd.DataFrame(comparison_data)

    # Gráfico de barras comparativo
    fig = go.Figure()

    fig.add_trace(go.Bar(
        name='Accuracy',
        x=df_comp['Symbol'],
        y=df_comp['Accuracy'],
        marker_color='#3498db'
    ))

    fig.add_trace(go.Bar(
        name='F1-Score',
        x=df_comp['Symbol'],
        y=df_comp['F1-Score'],
        marker_color='#e74c3c'
    ))

    fig.update_layout(
        title="Comparación de Métricas",
        xaxis_title="Modelo",
        yaxis_title="Score (%)",
        barmode='group',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)

    # Tabla comparativa
    st.dataframe(df_comp, use_container_width=True)
