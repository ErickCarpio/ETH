"""
Dashboard Web Simplificado - Multi-Model Management
Solo pestañas: Training, Signals, Models, Backtest
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).parent))

# Configuración de página
st.set_page_config(
    page_title="Multi-Model Trading Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main {
        background-color: #0E1117;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
        background-color: #262730;
        border-radius: 5px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1F6FEB;
    }
</style>
""", unsafe_allow_html=True)

# =================== IMPORTAR COMPONENTES ===================

try:
    from components.training_panel import render_training_panel
    from components.signals_panel import render_signals_panel
    from components.models_panel import render_models_panel
    from components.backtest_panel import render_backtest_panel
    panels_loaded = True
    panels_error = None
except Exception as e:
    panels_loaded = False
    panels_error = str(e)
    import traceback
    panels_traceback = traceback.format_exc()

# =================== HEADER ===================

st.title("🤖 Multi-Model Trading Dashboard")
st.markdown("Gestión de 20 modelos especializados para trading de criptomonedas")
st.markdown("---")

# =================== SIDEBAR ===================

st.sidebar.title("⚙️ Configuración")
st.sidebar.markdown("---")

# Info general
st.sidebar.header("📊 Sistema Multi-Modelo")
st.sidebar.info("""
**20 Modelos XGBoost Especializados**

Cada modelo entrenado específicamente para un par de trading con optimización Optuna.

Pares: ETH, SOL, BNB, XRP, ADA, DOGE, MATIC, DOT, LINK, UNI, ATOM, AVAX, LTC, ETC, FIL, APT, ARB, OP, INJ, SUI
""")

st.sidebar.markdown("---")

# Configuración de paths
st.sidebar.header("📁 Rutas del Sistema")

models_dir = st.sidebar.text_input(
    "Carpeta de modelos:",
    value="models",
    help="Carpeta donde se guardan los modelos entrenados"
)

data_dir = st.sidebar.text_input(
    "Carpeta de datos:",
    value="data/cache",
    help="Carpeta donde se almacenan los datos en cache"
)

st.sidebar.markdown("---")
st.sidebar.caption("Dashboard v2.0 - Multi-Model System")

# =================== TABS ===================

tab1, tab2, tab3, tab4 = st.tabs([
    "🧠 Training",
    "📡 Signals",
    "🔧 Models",
    "📈 Backtest"
])

# =================== TAB 1: TRAINING ===================

with tab1:
    if not panels_loaded:
        st.error(f"❌ Error cargando paneles: {panels_error}")
        st.code(panels_traceback)
    else:
        try:
            render_training_panel()
        except Exception as e:
            st.error(f"❌ Error en Training Panel: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 2: SIGNALS ===================

with tab2:
    if not panels_loaded:
        st.error(f"❌ Error cargando paneles: {panels_error}")
        st.code(panels_traceback)
    else:
        try:
            render_signals_panel()
        except Exception as e:
            st.error(f"❌ Error en Signals Panel: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 3: MODELS ===================

with tab3:
    if not panels_loaded:
        st.error(f"❌ Error cargando paneles: {panels_error}")
        st.code(panels_traceback)
    else:
        try:
            render_models_panel()
        except Exception as e:
            st.error(f"❌ Error en Models Panel: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 4: BACKTEST ===================

with tab4:
    if not panels_loaded:
        st.error(f"❌ Error cargando paneles: {panels_error}")
        st.code(panels_traceback)
    else:
        try:
            render_backtest_panel()
        except Exception as e:
            st.error(f"❌ Error en Backtest Panel: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
