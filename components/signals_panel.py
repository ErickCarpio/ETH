"""
Signals Panel
Panel para generar y ejecutar señales diarias
"""

import streamlit as st
import pandas as pd
import sys
import subprocess
import asyncio
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))


def render_signals_panel():
    """Renderiza el panel de señales"""

    st.header("📡 Señales Diarias")

    # Panel de generación
    render_signal_generation()

    st.markdown("---")

    # Panel de resultados
    render_signal_results()

    st.markdown("---")

    # Historial
    render_signal_history()


def render_signal_generation():
    """Renderiza interfaz de generación de señales"""

    st.subheader("⚙️ Generar Señales")

    col1, col2 = st.columns(2)

    with col1:
        num_pairs = st.slider("Número de pares:", 5, 20, 20, step=1)

    with col2:
        min_confidence = st.slider("Threshold mínimo:", 0.60, 0.90, 0.70, step=0.05)

    st.info(f"📊 Se analizarán los top {num_pairs} pares por volumen")

    # Botón generar
    if st.button("📡 Generar Señales", type="primary"):
        generate_signals(num_pairs, min_confidence)


def generate_signals(num_pairs, min_confidence):
    """Genera señales"""

    with st.spinner(f"Generando señales para {num_pairs} pares..."):
        st.info("📊 Analizando mercado...")

        # TODO: Ejecutar daily_signals.py en subprocess
        # Por ahora, mostrar instrucciones
        st.code(f"""
# Ejecuta este comando en terminal:
python daily_signals.py --pairs {num_pairs}

# Las señales se guardarán en: signals/signals_YYYYMMDD_HHMMSS.csv
# El threshold mínimo ({min_confidence}) se puede configurar en config_15min.json
        """, language="bash")

        st.success("✅ Revisa el terminal para ver el progreso")


def render_signal_results():
    """Renderiza resultados de señales generadas"""

    st.subheader("📊 Señales Generadas")

    # Buscar archivo de señales más reciente
    signals_dir = Path('signals')

    if not signals_dir.exists():
        st.info("ℹ️ No hay señales generadas. Genera señales primero.")
        return

    signal_files = sorted(signals_dir.glob('signals_*.csv'), reverse=True)

    if not signal_files:
        st.info("ℹ️ No hay señales generadas. Genera señales primero.")
        return

    # Selector de archivo
    selected_file = st.selectbox(
        "Selecciona archivo de señales:",
        [f.name for f in signal_files[:10]]  # Últimos 10
    )

    if not selected_file:
        return

    # Cargar señales
    try:
        df = pd.read_csv(signals_dir / selected_file)

        if df.empty:
            st.warning("⚠️ El archivo no contiene señales")
            return

        # Filtros
        col1, col2 = st.columns(2)

        with col1:
            min_conf = st.slider("Filtrar por confianza:", 0.0, 1.0, 0.70, step=0.05, key="filter_conf")

        with col2:
            direction = st.selectbox("Filtrar por dirección:", ["Todas", "LONG", "SHORT"])

        # Aplicar filtros
        filtered_df = df[df['confidence'] >= min_conf]

        if direction != "Todas":
            filtered_df = filtered_df[filtered_df['direction'] == direction]

        # Mostrar tabla
        st.markdown(f"### 🎯 Señales de Alta Confianza (>={min_conf:.0%})")

        st.dataframe(
            filtered_df[[
                'symbol', 'direction', 'confidence', 'current_price',
                'entry', 'take_profit', 'stop_loss', 'expected_value', 'probability'
            ]].style.format({
                'confidence': '{:.1%}',
                'current_price': '${:.2f}',
                'entry': '${:.2f}',
                'take_profit': '${:.2f}',
                'stop_loss': '${:.2f}',
                'expected_value': '{:.2f}',
                'probability': '{:.1%}'
            }),
            use_container_width=True,
            height=400
        )

        # Resumen
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Señales", len(filtered_df))

        with col2:
            longs = len(filtered_df[filtered_df['direction'] == 'LONG'])
            st.metric("LONG", longs)

        with col3:
            shorts = len(filtered_df[filtered_df['direction'] == 'SHORT'])
            st.metric("SHORT", shorts)

        # Botones de acción
        col1, col2 = st.columns(2)

        with col1:
            if st.button("📥 Descargar CSV", type="secondary"):
                st.download_button(
                    label="💾 Guardar CSV",
                    data=filtered_df.to_csv(index=False),
                    file_name=f"filtered_{selected_file}",
                    mime="text/csv"
                )

        with col2:
            if st.button("🚀 Ejecutar Señales", type="primary"):
                execute_signals(signals_dir / selected_file, min_conf)

    except Exception as e:
        st.error(f"❌ Error cargando señales: {e}")


def execute_signals(signals_file, min_confidence):
    """Ejecuta señales en Binance Demo"""

    st.warning("⚠️ CONFIRMACIÓN DE EJECUCIÓN")

    try:
        df = pd.read_csv(signals_file)
        filtered = df[df['confidence'] >= min_confidence]

        st.markdown(f"### Se ejecutarán {len(filtered)} trades en Binance Demo SPOT:")

        st.dataframe(
            filtered[['symbol', 'direction', 'confidence', 'entry', 'take_profit', 'stop_loss']],
            use_container_width=True
        )

        # Mostrar advertencia
        st.info("ℹ️ Las órdenes se ejecutarán en **Binance Testnet (SPOT)** con dinero ficticio")

        confirm = st.checkbox("✅ Confirmo que quiero ejecutar estos trades en Binance Demo")

        if confirm:
            if st.button("🚀 Ejecutar Ahora", type="primary", key="execute_now_btn"):
                with st.spinner("Ejecutando trades en Binance Demo..."):
                    try:
                        # Ejecutar script en modo non-interactive
                        # Crear archivo temporal con confirmación
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                            f.write('yes\n')
                            confirm_file = f.name

                        # Ejecutar script
                        result = subprocess.run(
                            ['python', 'execute_signals.py', str(signals_file),
                             '--min-confidence', str(min_confidence)],
                            capture_output=True,
                            text=True,
                            stdin=open(confirm_file, 'r'),
                            timeout=60
                        )

                        # Limpiar archivo temporal
                        Path(confirm_file).unlink(missing_ok=True)

                        # Mostrar resultados
                        if result.returncode == 0:
                            st.success("✅ Trades ejecutados exitosamente!")

                            # Mostrar log
                            with st.expander("📋 Ver log de ejecución"):
                                st.code(result.stdout, language="bash")

                            # Buscar archivo de log generado
                            signals_dir = Path('signals')
                            executed_files = sorted(signals_dir.glob('executed_*.csv'), reverse=True)
                            if executed_files:
                                st.success(f"📁 Log guardado: {executed_files[0].name}")
                        else:
                            st.error("❌ Error ejecutando trades")
                            st.code(result.stderr, language="bash")

                    except subprocess.TimeoutExpired:
                        st.error("❌ Timeout: La ejecución tardó demasiado")
                    except Exception as e:
                        st.error(f"❌ Error ejecutando: {e}")
                        import traceback
                        st.code(traceback.format_exc(), language="bash")

    except Exception as e:
        st.error(f"❌ Error: {e}")


def render_signal_history():
    """Renderiza historial de señales"""

    st.subheader("📂 Historial de Señales")

    signals_dir = Path('signals')

    if not signals_dir.exists() or not list(signals_dir.glob('signals_*.csv')):
        st.info("ℹ️ No hay historial de señales")
        return

    signal_files = sorted(signals_dir.glob('signals_*.csv'), reverse=True)

    # Tabla de archivos
    files_data = []

    for f in signal_files[:20]:  # Últimos 20
        try:
            df = pd.read_csv(f)
            files_data.append({
                'Archivo': f.name,
                'Señales': len(df),
                'Alta Confianza (>=70%)': len(df[df['confidence'] >= 0.70]),
                'Fecha': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            })
        except:
            continue

    if files_data:
        st.dataframe(pd.DataFrame(files_data), use_container_width=True, height=300)
