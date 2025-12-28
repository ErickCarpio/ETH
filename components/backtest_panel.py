"""
Backtest Panel
Panel para ejecutar backtests históricos
"""

import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.model_loader import ModelLoader


def render_backtest_panel():
    """Renderiza el panel de backtesting"""

    st.header("📈 Backtesting")

    # Configuración
    render_backtest_config()

    st.markdown("---")

    # Resultados (si existen)
    render_backtest_results()


def render_backtest_config():
    """Renderiza configuración de backtest"""

    st.subheader("⚙️ Configuración del Backtest")

    # Verificar modelos disponibles
    model_loader = ModelLoader()
    models = model_loader.list_models()

    if not models:
        st.warning("⚠️ No hay modelos entrenados. Ve a la pestaña Training.")
        return

    col1, col2 = st.columns(2)

    with col1:
        # Selector de modelo
        selected_symbol = st.selectbox(
            "Modelo:",
            [m['symbol'] for m in models]
        )

        # Período de backtest
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        date_range = st.date_input(
            "Período:",
            value=(start_date, end_date),
            max_value=end_date
        )

    with col2:
        # Threshold
        threshold = st.slider(
            "Threshold de confianza:",
            0.60, 0.90, 0.70, 0.05
        )

        # Stop Loss
        sl_pct = st.slider(
            "Stop Loss (%):",
            0.5, 5.0, 2.0, 0.5
        ) / 100

        # Take Profit
        tp_pct = st.slider(
            "Take Profit (%):",
            1.0, 10.0, 5.0, 0.5
        ) / 100

    # Info del modelo
    if selected_symbol:
        meta = model_loader.get_model_metadata(selected_symbol)
        if meta:
            st.info(f"📊 Modelo entrenado con accuracy: {meta.get('test_accuracy', 0) * 100:.1f}%")

    # Botón ejecutar
    if st.button("🧪 Ejecutar Backtest", type="primary"):
        run_backtest(selected_symbol, date_range, threshold, sl_pct, tp_pct)


def run_backtest(symbol, date_range, threshold, sl_pct, tp_pct):
    """Ejecuta backtest"""

    with st.spinner("Ejecutando backtest..."):
        st.info(f"📊 Backtesting {symbol}...")
        st.info(f"📅 Período: {date_range[0]} a {date_range[1]}")
        st.info(f"⚙️ Threshold: {threshold:.0%}, SL: {sl_pct:.1%}, TP: {tp_pct:.1%}")

        # TODO: Ejecutar backtest real
        # Por ahora, mostrar instrucciones
        st.code(f"""
# Ejecuta este comando en terminal:
python -c "
from backtesting.backtester import Backtester
import pandas as pd

# Cargar modelo
# Cargar datos históricos
# Ejecutar backtest
# Guardar resultados
"

# O implementar interfaz de backtest completa
        """, language="bash")

        st.success("✅ Backtest completado (simulado)")

        # Generar datos de ejemplo para demostración
        generate_example_backtest()


def generate_example_backtest():
    """Genera backtest de ejemplo para demostración"""

    import numpy as np

    # Datos de ejemplo
    np.random.seed(42)

    n_trades = 45
    win_rate = 0.622

    wins = int(n_trades * win_rate)
    losses = n_trades - wins

    # P&L aleatorios
    win_pnls = np.random.normal(3.2, 1.5, wins)
    loss_pnls = np.random.normal(-1.8, 0.8, losses)

    all_pnls = np.concatenate([win_pnls, loss_pnls])
    np.random.shuffle(all_pnls)

    # Guardar en session state
    st.session_state['backtest_results'] = {
        'total_trades': n_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': all_pnls.sum(),
        'profit_factor': abs(win_pnls.sum() / loss_pnls.sum()),
        'avg_win': win_pnls.mean(),
        'avg_loss': loss_pnls.mean(),
        'max_drawdown': -8.5,
        'sharpe': 1.42,
        'pnl_series': all_pnls,
        'equity_curve': np.cumsum(all_pnls)
    }

    st.rerun()


def render_backtest_results():
    """Renderiza resultados de backtest"""

    if 'backtest_results' not in st.session_state:
        return

    results = st.session_state['backtest_results']

    st.subheader("📊 Resultados del Backtest")

    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Trades", results['total_trades'])
        st.metric("Wins / Losses", f"{results['wins']} / {results['losses']}")

    with col2:
        st.metric("Win Rate", f"{results['win_rate'] * 100:.1f}%")
        st.metric("P&L Total", f"{results['total_pnl']:+.1f}%", delta=f"{results['total_pnl']:.1f}%")

    with col3:
        st.metric("Profit Factor", f"{results['profit_factor']:.2f}")
        st.metric("Avg Win", f"{results['avg_win']:+.1f}%")

    with col4:
        st.metric("Max Drawdown", f"{results['max_drawdown']:.1f}%")
        st.metric("Avg Loss", f"{results['avg_loss']:.1f}%")

    # Sharpe Ratio
    st.metric("📊 Sharpe Ratio", f"{results['sharpe']:.2f}")

    st.markdown("---")

    # Gráficos
    render_backtest_charts(results)

    # Botón descargar
    if st.button("📥 Descargar Resultados"):
        download_backtest_results(results)


def render_backtest_charts(results):
    """Renderiza gráficos de backtest"""

    # Crear subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=('Equity Curve', 'Individual Trade P&L'),
        row_heights=[0.6, 0.4]
    )

    # Equity curve
    fig.add_trace(
        go.Scatter(
            x=list(range(len(results['equity_curve']))),
            y=results['equity_curve'],
            mode='lines',
            name='Equity',
            line=dict(color='#3498db', width=2),
            fill='tozeroy',
            fillcolor='rgba(52, 152, 219, 0.2)'
        ),
        row=1, col=1
    )

    # Línea en 0
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)

    # P&L individual
    colors = ['#27AE60' if x > 0 else '#E74C3C' for x in results['pnl_series']]

    fig.add_trace(
        go.Bar(
            x=list(range(len(results['pnl_series']))),
            y=results['pnl_series'],
            name='Trade P&L',
            marker_color=colors
        ),
        row=2, col=1
    )

    # Layout
    fig.update_layout(
        height=700,
        showlegend=False,
        template='plotly_white'
    )

    fig.update_xaxes(title_text="Trade #", row=2, col=1)
    fig.update_yaxes(title_text="P&L Acumulado (%)", row=1, col=1)
    fig.update_yaxes(title_text="P&L (%)", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # Distribución de P&L
    st.markdown("### 📊 Distribución de P&L")

    fig_hist = go.Figure(data=[
        go.Histogram(
            x=results['pnl_series'],
            nbinsx=20,
            marker_color='#3498db',
            opacity=0.7
        )
    ])

    fig_hist.update_layout(
        title="Distribución de Resultados por Trade",
        xaxis_title="P&L (%)",
        yaxis_title="Frecuencia",
        height=300,
        template='plotly_white'
    )

    st.plotly_chart(fig_hist, use_container_width=True)


def download_backtest_results(results):
    """Descarga resultados de backtest"""

    # Crear CSV con resultados
    trades_df = pd.DataFrame({
        'Trade #': range(1, len(results['pnl_series']) + 1),
        'P&L (%)': results['pnl_series'],
        'Cumulative P&L (%)': results['equity_curve']
    })

    csv = trades_df.to_csv(index=False)

    st.download_button(
        label="💾 Descargar CSV",
        data=csv,
        file_name=f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
