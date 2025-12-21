"""
Dashboard Web para Trading Bot - Visualización en Tiempo Real
Ejecutar con: streamlit run web_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
from pathlib import Path
import time
from datetime import datetime, timedelta
import numpy as np

# Configuración de página
st.set_page_config(
    page_title="ETH Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .profit { color: #27AE60; font-weight: bold; }
    .loss { color: #E74C3C; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# =================== FUNCIONES AUXILIARES ===================

@st.cache_data(ttl=60)
def load_price_data(hours=24):
    """Carga datos de precio desde cache"""
    try:
        cache_files = list(Path('data/cache').glob('ETHUSDT_1h_*.parquet'))
        if cache_files:
            latest = max(cache_files, key=lambda x: x.stat().st_mtime)
            df = pd.read_parquet(latest)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
            # Últimas N horas
            cutoff = datetime.now() - timedelta(hours=hours)
            df = df[df.index >= cutoff]
            return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
    return pd.DataFrame()

def load_model_info():
    """Carga información del modelo"""
    try:
        model_path = Path('models/xgboost_model.json')
        if model_path.exists():
            mod_time = datetime.fromtimestamp(model_path.stat().st_mtime)
            return {
                'exists': True,
                'last_trained': mod_time,
                'age_hours': (datetime.now() - mod_time).total_seconds() / 3600
            }
    except:
        pass
    return {'exists': False}

def load_trades_history():
    """Carga historial de trades (simulado por ahora)"""
    # TODO: Cargar desde archivo real cuando el bot esté corriendo
    try:
        trades_file = Path('logs/trades_history.csv')
        if trades_file.exists():
            return pd.read_csv(trades_file)
    except:
        pass

    # Datos de ejemplo para visualización
    return pd.DataFrame({
        'entry_time': pd.date_range(end=datetime.now(), periods=10, freq='6h'),
        'exit_time': pd.date_range(end=datetime.now(), periods=10, freq='6h') + pd.Timedelta(hours=2),
        'direction': ['LONG', 'SHORT'] * 5,
        'entry_price': [3500, 3520, 3480, 3510, 3490, 3505, 3515, 3495, 3500, 3510],
        'exit_price': [3550, 3500, 3530, 3490, 3540, 3485, 3565, 3480, 3550, 3500],
        'pnl_pct': [1.4, 0.6, 1.4, -0.6, 1.4, -0.6, 1.4, -0.4, 1.4, -0.3],
        'exit_reason': ['TP', 'TP', 'TP', 'SL', 'TP', 'SL', 'TP', 'SL', 'TP', 'SL']
    })

def load_config():
    """Carga configuración"""
    try:
        with open('config_15min.json', 'r') as f:
            return json.load(f)
    except:
        return {}

# =================== SIDEBAR ===================

st.sidebar.title("⚙️ Control Panel")

# Estado del bot
st.sidebar.header("🤖 Estado del Bot")
bot_status = st.sidebar.empty()
bot_status.success("🟢 Bot Iniciado" if st.session_state.get('bot_running', False) else "🔴 Bot Detenido")

# Controles
col1, col2 = st.sidebar.columns(2)
if col1.button("▶️ Iniciar", width="stretch"):
    st.session_state['bot_running'] = True
    st.rerun()

if col2.button("⏸️ Detener", width="stretch"):
    st.session_state['bot_running'] = False
    st.rerun()

# Configuración
st.sidebar.header("📊 Configuración")
config = load_config()

threshold = st.sidebar.slider(
    "Threshold de Confianza",
    min_value=0.5,
    max_value=0.95,
    value=config.get('trading', {}).get('prediction_threshold', 0.70),
    step=0.05
)

sl_pct = st.sidebar.slider(
    "Stop Loss %",
    min_value=0.01,
    max_value=0.05,
    value=config.get('trading', {}).get('stop_loss_pct', 0.02),
    step=0.005,
    format="%.3f"
)

tp_pct = st.sidebar.slider(
    "Take Profit %",
    min_value=0.02,
    max_value=0.10,
    value=config.get('trading', {}).get('take_profit_pct', 0.05),
    step=0.005,
    format="%.3f"
)

# Timeframe selector
st.sidebar.header("⏱️ Timeframe")
hours_to_show = st.sidebar.selectbox(
    "Mostrar últimas:",
    [6, 12, 24, 48, 72, 168],
    index=2,
    format_func=lambda x: f"{x} horas" if x < 168 else f"{x//24} días"
)

# Auto-refresh
auto_refresh = st.sidebar.checkbox("🔄 Auto-actualizar", value=True)
if auto_refresh:
    refresh_rate = st.sidebar.slider("Cada (segundos):", 5, 60, 10)

# =================== HEADER ===================

st.title("📈 ETH Trading Bot Dashboard")
st.markdown("---")

# Métricas principales
col1, col2, col3, col4, col5 = st.columns(5)

# Cargar datos
df_price = load_price_data(hours=hours_to_show)
trades_df = load_trades_history()
model_info = load_model_info()

# Precio actual
if not df_price.empty:
    current_price = df_price['close'].iloc[-1]
    prev_price = df_price['close'].iloc[-25] if len(df_price) > 25 else df_price['close'].iloc[0]
    price_change = ((current_price - prev_price) / prev_price) * 100

    col1.metric(
        "💵 Precio ETH",
        f"${current_price:,.2f}",
        f"{price_change:+.2f}% (24h)"
    )

# Trades totales
total_trades = len(trades_df)
wins = len(trades_df[trades_df['pnl_pct'] > 0])
losses = total_trades - wins
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

col2.metric(
    "📊 Trades Totales",
    total_trades,
    f"Win Rate: {win_rate:.1f}%"
)

# P&L Total
total_pnl = trades_df['pnl_pct'].sum() if not trades_df.empty else 0
col3.metric(
    "💰 P&L Total",
    f"{total_pnl:+.2f}%",
    "En últimas 24h"
)

# Profit Factor
wins_sum = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].sum()
losses_sum = abs(trades_df[trades_df['pnl_pct'] < 0]['pnl_pct'].sum())
profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0

col4.metric(
    "📈 Profit Factor",
    f"{profit_factor:.2f}",
    "Ganancias/Pérdidas"
)

# Modelo
if model_info['exists']:
    age_str = f"{model_info['age_hours']:.1f}h ago"
    col5.metric(
        "🧠 Modelo",
        "Actualizado",
        age_str
    )
else:
    col5.metric("🧠 Modelo", "No Entrenado", "❌")

st.markdown("---")

# =================== GRÁFICO PRINCIPAL ===================

st.header("📊 Gráfico de Trading")

if not df_price.empty:
    # Crear figura con subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=('Precio + Trades', 'P&L Acumulado')
    )

    # === Panel 1: Candlestick + Trades ===
    fig.add_trace(
        go.Candlestick(
            x=df_price.index,
            open=df_price['open'],
            high=df_price['high'],
            low=df_price['low'],
            close=df_price['close'],
            name='ETH/USDT',
            increasing_line_color='#27AE60',
            decreasing_line_color='#E74C3C'
        ),
        row=1, col=1
    )

    # Agregar trades como markers
    for _, trade in trades_df.iterrows():
        entry_time = pd.to_datetime(trade['entry_time'])
        exit_time = pd.to_datetime(trade['exit_time'])

        # Solo mostrar si está en el rango visible
        if entry_time < df_price.index[0]:
            continue

        is_win = trade['pnl_pct'] > 0
        color = '#27AE60' if is_win else '#E74C3C'

        # Marker de entrada
        fig.add_trace(
            go.Scatter(
                x=[entry_time],
                y=[trade['entry_price']],
                mode='markers',
                marker=dict(
                    symbol='triangle-up' if trade['direction'] == 'LONG' else 'triangle-down',
                    size=15,
                    color=color,
                    line=dict(width=2, color='white')
                ),
                name=f"{trade['direction']} Entry",
                showlegend=False,
                hovertemplate=f"<b>{trade['direction']} Entry</b><br>" +
                              f"Price: ${trade['entry_price']:.2f}<br>" +
                              f"Time: {entry_time}<extra></extra>"
            ),
            row=1, col=1
        )

        # Marker de salida
        fig.add_trace(
            go.Scatter(
                x=[exit_time],
                y=[trade['exit_price']],
                mode='markers',
                marker=dict(
                    symbol='triangle-down' if trade['direction'] == 'LONG' else 'triangle-up',
                    size=15,
                    color=color,
                    line=dict(width=2, color='white')
                ),
                name=f"{trade['direction']} Exit",
                showlegend=False,
                hovertemplate=f"<b>{trade['direction']} Exit ({trade['exit_reason']})</b><br>" +
                              f"Price: ${trade['exit_price']:.2f}<br>" +
                              f"P&L: {trade['pnl_pct']:+.2f}%<br>" +
                              f"Time: {exit_time}<extra></extra>"
            ),
            row=1, col=1
        )

        # Línea conectando entrada/salida
        fig.add_trace(
            go.Scatter(
                x=[entry_time, exit_time],
                y=[trade['entry_price'], trade['exit_price']],
                mode='lines',
                line=dict(color=color, width=1, dash='dot'),
                showlegend=False,
                hoverinfo='skip'
            ),
            row=1, col=1
        )

    # === Panel 2: P&L Acumulado ===
    if not trades_df.empty:
        trades_sorted = trades_df.sort_values('exit_time')
        trades_sorted['cumulative_pnl'] = trades_sorted['pnl_pct'].cumsum()

        fig.add_trace(
            go.Scatter(
                x=pd.to_datetime(trades_sorted['exit_time']),
                y=trades_sorted['cumulative_pnl'],
                mode='lines',
                name='P&L Acumulado',
                line=dict(color='#16A085', width=2),
                fill='tozeroy',
                fillcolor='rgba(22, 160, 133, 0.2)'
            ),
            row=2, col=1
        )

        # Línea en 0
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)

    # Layout
    fig.update_layout(
        height=800,
        showlegend=True,
        hovermode='x unified',
        xaxis_rangeslider_visible=False,
        template='plotly_white'
    )

    fig.update_xaxes(title_text="Fecha", row=2, col=1)
    fig.update_yaxes(title_text="Precio (USDT)", row=1, col=1)
    fig.update_yaxes(title_text="P&L Acumulado (%)", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("⚠️ No hay datos de precio disponibles. Ejecuta primero el pipeline de entrenamiento.")

# =================== TABLA DE TRADES ===================

st.header("📋 Historial de Trades")

if not trades_df.empty:
    # Formatear DataFrame para mostrar
    display_df = trades_df.copy()
    display_df['entry_time'] = pd.to_datetime(display_df['entry_time']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['exit_time'] = pd.to_datetime(display_df['exit_time']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['entry_price'] = display_df['entry_price'].apply(lambda x: f"${x:.2f}")
    display_df['exit_price'] = display_df['exit_price'].apply(lambda x: f"${x:.2f}")
    display_df['pnl_pct'] = display_df['pnl_pct'].apply(lambda x: f"{x:+.2f}%")

    # Renombrar columnas
    display_df.columns = ['Entrada', 'Salida', 'Dirección', 'Precio Entrada', 'Precio Salida', 'P&L %', 'Razón']

    st.dataframe(
        display_df,
        width="stretch",
        height=400
    )
else:
    st.info("No hay trades registrados aún.")

# =================== ESTADÍSTICAS ===================

col1, col2 = st.columns(2)

with col1:
    st.header("📊 Estadísticas de Trading")

    if not trades_df.empty:
        # Keep data as numbers, format in display
        avg_win = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean()
        avg_loss = trades_df[trades_df['pnl_pct'] < 0]['pnl_pct'].mean()
        best_trade = trades_df['pnl_pct'].max()
        worst_trade = trades_df['pnl_pct'].min()

        # Create DataFrame with formatted strings only
        stats_display = pd.DataFrame({
            'Métrica': ['Total Trades', 'Wins', 'Losses', 'Win Rate', 'Avg Win', 'Avg Loss', 'Best Trade', 'Worst Trade', 'Profit Factor'],
            'Valor': [
                str(total_trades),
                str(wins),
                str(losses),
                f"{win_rate:.1f}%",
                f"{avg_win:.2f}%",
                f"{avg_loss:.2f}%",
                f"{best_trade:.2f}%",
                f"{worst_trade:.2f}%",
                f"{profit_factor:.2f}"
            ]
        })

        st.table(stats_display.set_index('Métrica'))

with col2:
    st.header("⚙️ Configuración Actual")

    # Create DataFrame with formatted strings only
    config_display = pd.DataFrame({
        'Parámetro': ['Threshold', 'Stop Loss', 'Take Profit', 'Timeframe', 'Max Positions', 'Position Size'],
        'Valor': [
            f"{threshold:.0%}",
            f"{sl_pct:.1%}",
            f"{tp_pct:.1%}",
            '1 hora',
            str(config.get('trading', {}).get('max_positions', 1)),
            f"${config.get('trading', {}).get('position_size_usd', 100)}"
        ]
    })

    st.table(config_display.set_index('Parámetro'))

# =================== FOOTER ===================

st.markdown("---")
st.caption(f"🕒 Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Auto-refresh
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
