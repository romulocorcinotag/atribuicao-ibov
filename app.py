"""
Atribuição de Performance — IBOV + Synta FIA / FIA II
TAG Investimentos
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os, glob, json, base64, re, io, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from collections import defaultdict

# ==============================================================================
# CONFIG
# ==============================================================================
st.set_page_config(
    page_title="Atribuição de Performance - TAG Investimentos",
    page_icon="https://taginvest.com.br/favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SSO Authentication Guard ──
from sso_auth import require_sso
sso_user = require_sso()

# ==============================================================================
# PATHS
# ==============================================================================
XML_BASE = r"G:\Drives compartilhados\SisIntegra\AMBIENTE_PRODUCAO\Posicao_XML\Mellon"
CARTEIRA_RV_DATA = r"G:\Drives compartilhados\Gestao_AI\carteira_rv\data"
CARTEIRA_RV_CACHE = r"G:\Drives compartilhados\Gestao_AI\carteira_rv\cache"
XML_FECHAMENTO = r"G:\Drives compartilhados\Arquivos_XML_Fechamento"

# Cloud mode: use pre-exported parquets when local XMLs not available
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HAS_LOCAL_XML = os.path.isdir(XML_BASE)
HAS_PARQUET_DATA = os.path.isdir(DATA_DIR) and any(f.endswith(".parquet") for f in os.listdir(DATA_DIR) if "timeseries" in f)

FUNDOS_CONFIG = {
    "Synta FIA II": {"cnpj": "51564188000131", "xml_prefix": "FD51564188000131"},
    "Synta FIA": {"cnpj": "20214858000166", "xml_prefix": "FD20214858000166"},
}

SUBFUNDO_NAMES = {
    # --- Synta FIA II sub-fundos (10) ---
    "15578434000140": "Atmos Institucional",
    "28408121000196": "GTI Haifa FIA",
    "11961199000130": "Neo Navitas FIC FIA",
    "42831345000137": "NV FC FIA",
    "17157131000180": "Oceana Selection FIC",
    "26956042000194": "Oceana Valor 30 FIC",
    "49984812000108": "Organon Institucional",
    "13455174000190": "Santander Dividendos",
    "17898543000170": "BNY ARX Liquidez RF",
    "16565084000140": "SPX Apache FIA",
    # --- Synta FIA sub-fundos (8, 2 compartilhados acima) ---
    "53827819000193": "Absolute Pace FIC FIM",
    "51427627000164": "Atmos Institucional S",
    "52070019000108": "Real Investor Inst FIA",
    "40226121000170": "Perfin Infra Equity FIA",
    "41632880000104": "SPX Falcon Inst MM",
    "39346123000114": "Tarpon GT Institucional",
    # --- Synta funds themselves (for Desempenho Individual) ---
    "51564188000131": "Synta FIA II",
    "20214858000166": "Synta FIA",
}

# Classificacao de componentes para atribuicao
# BNY ARX Liquidez = Caixa conforme usuario
COMPONENTE_CLASSE = {
    "BNY ARX Liquidez RF": "Caixa",
    "SPX Apache FIA": "Renda Fixa",
    "Renda Fixa (LFT)": "Renda Fixa",
    "Caixa": "Caixa",
}

# ETF -> Indice B3
ETF_INDEX_MAP = {
    "BOVA11": "IBOV", "SMAL11": "SMLL", "BOVV11": "IBOV", "BOVB11": "IBOV",
    "DIVO11": "IDIV", "BRAX11": "IBRX", "PIBB11": "IBXX", "MATB11": "IMAT",
    "FIND11": "IFNC", "ISUS11": "ISEE", "ECOO11": "ICO2", "GOVE11": "IGCT",
    "UTIP11": "UTIL", "IVVB11": "S&P500", "HASH11": "CRYPTO", "XFIX11": "IFIX",
    "LVOL11": "IBOV",
}

# ==============================================================================
# TAG BRAND
# ==============================================================================
TAG_VERMELHO = "#630D24"
TAG_VERMELHO_LIGHT = "#8B1A3A"
TAG_VERMELHO_DARK = "#3D0816"
TAG_OFFWHITE = "#E6E4DB"
TAG_LARANJA = "#FF8853"
TAG_LARANJA_DARK = "#E06B35"
TAG_BG_DARK = "#1A0A10"
TAG_BG_CARD = "#2A1520"
TAG_BG_CARD_ALT = "#321A28"
TEXT_COLOR = TAG_OFFWHITE
TEXT_MUTED = "#9A9590"
BORDER_COLOR = f"{TAG_VERMELHO}30"
CHART_GRID = "rgba(230,228,219,0.08)"
TAG_CHART_COLORS = [
    "#FF8853", "#5C85F7", "#6BDE97", "#FFBB00", "#ED5A6E",
    "#58C6F5", "#A485F2", "#477C88", "#002A6E", "#6A6864",
]
GREEN = "#6BDE97"
RED = "#ED5A6E"

# ==============================================================================
# CSS
# ==============================================================================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', 'Tahoma', sans-serif; }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {TAG_VERMELHO_DARK} 0%, {TAG_BG_DARK} 100%);
        border-right: 1px solid {TAG_VERMELHO}33;
    }}
    [data-testid="stSidebar"] .stRadio label {{ font-size: 0.9rem; padding: 6px 0; }}
    h1 {{ color: {TAG_OFFWHITE} !important; font-weight: 600 !important;
         border-bottom: 2px solid {TAG_LARANJA}40; padding-bottom: 12px !important; }}
    h2, h3 {{ color: {TAG_OFFWHITE} !important; font-weight: 500 !important; }}
    .tag-metric-card {{
        background: linear-gradient(135deg, {TAG_BG_CARD} 0%, {TAG_BG_CARD_ALT} 100%);
        border: 1px solid {TAG_VERMELHO}30; border-radius: 12px;
        padding: 16px 20px; text-align: center;
        box-shadow: 0 4px 16px rgba(99,13,36,0.15);
    }}
    .tag-metric-card .label {{ color: {TEXT_MUTED}; font-size: 0.75rem;
        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
    .tag-metric-card .value {{ color: {TAG_OFFWHITE}; font-size: 1.4rem; font-weight: 600; }}
    .tag-section-title {{
        font-size: 1.05rem; font-weight: 600; color: {TAG_LARANJA};
        margin: 24px 0 12px 0; padding-bottom: 6px;
        border-bottom: 1px solid {TAG_VERMELHO}25;
    }}
    .tag-disclaimer {{
        background: {TAG_BG_CARD}; border: 1px solid {BORDER_COLOR};
        border-radius: 8px; padding: 12px 16px; margin-top: 16px;
        font-size: 12px; color: {TEXT_MUTED};
    }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; border-bottom: 2px solid {TAG_VERMELHO}30; }}
    .stTabs [data-baseweb="tab"] {{ border-radius: 8px 8px 0 0; padding: 8px 24px; font-weight: 500; }}
    .stTabs [aria-selected="true"] {{ background: {TAG_VERMELHO}20 !important;
        border-bottom: 3px solid {TAG_LARANJA} !important; }}
    hr {{ border-color: {TAG_VERMELHO}25 !important; }}
    [data-testid="stSidebar"] .stCaption {{ color: {TEXT_MUTED} !important; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    _logo_path = os.path.join(os.path.dirname(__file__), "logo_sidebar.png")
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _f:
            _logo_b64 = base64.b64encode(_f.read()).decode()
        st.markdown(f"""<div style='text-align:center; padding: 12px 0 8px 0;'>
            <img src='data:image/png;base64,{_logo_b64}' style='width:160px; height:auto; margin-bottom:6px;'/>
            <div style='width:40px; height:2px; background:{TAG_LARANJA}; margin:6px auto 0;'></div>
            <div style='font-size:0.75rem; color:{TAG_LARANJA}; margin-top:8px; font-weight:500;'>
            Atribuição de Performance</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style='text-align:center; padding: 8px 0 16px 0;'>
            <div style='font-size:1.5rem; font-weight:700; color:{TAG_OFFWHITE};'>TAG</div>
            <div style='font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:{TEXT_MUTED}; margin-top:-4px;'>Investimentos</div>
            <div style='width:40px; height:2px; background:{TAG_LARANJA}; margin:10px auto 0;'></div>
            <div style='font-size:0.75rem; color:{TAG_LARANJA}; margin-top:8px; font-weight:500;'>
            Atribuição de Performance</div></div>""", unsafe_allow_html=True)
    st.divider()
    page_sel = st.radio("Navegação", [
        "📊 Atribuição IBOV",
        "📈 Synta FIA / FIA II",
        "🔬 Brinson-Fachler",
        "⚖️ Comparativo Fundos vs IBOV",
        "🔍 Carteira Explodida por Ativo",
        "📉 Desempenho Individual",
    ], label_visibility="collapsed")
    st.divider()
    st.caption("Fonte preços: Yahoo Finance")
    st.caption("Composição IBOV: API B3")
    st.caption("Posicoes: XML BNY Mellon + CVM")
    st.caption(f"Atualizado: {date.today().strftime('%d/%m/%Y')}")

# ==============================================================================
# HELPERS
# ==============================================================================
def metric_card(label, value):
    return f'<div class="tag-metric-card"><div class="label">{label}</div><div class="value">{value}</div></div>'

def _chart_layout(fig, title="", height=450, y_title="", y_suffix="", margin_b=50):
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=TAG_LARANJA, family="Inter, Tahoma"),
                   y=0.98, yanchor="top") if title else {},
        height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Tahoma, sans-serif", color=TAG_OFFWHITE, size=12),
        margin=dict(t=40 if title else 20, b=margin_b, l=60, r=20),
        xaxis=dict(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID,
                   showline=True, linecolor="rgba(230,228,219,0.15)", linewidth=1),
        yaxis=dict(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID,
                   showline=True, linecolor="rgba(230,228,219,0.15)", linewidth=1,
                   title=y_title, ticksuffix=y_suffix),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        colorway=TAG_CHART_COLORS,
        hoverlabel=dict(bgcolor=TAG_BG_CARD, font_size=12, font_color=TAG_OFFWHITE),
    )
    return fig

# ==============================================================================
# SETOR MAP
# ==============================================================================
SETOR_MAP = {
    'ITUB4': 'Financeiro', 'ITUB3': 'Financeiro', 'BBDC4': 'Financeiro', 'BBDC3': 'Financeiro',
    'BBAS3': 'Financeiro', 'SANB11': 'Financeiro', 'B3SA3': 'Financeiro', 'BPAC11': 'Financeiro',
    'CIEL3': 'Financeiro', 'PSSA3': 'Financeiro', 'BBSE3': 'Financeiro', 'IRBR3': 'Financeiro',
    'SULA11': 'Financeiro', 'CXSE3': 'Financeiro', 'ABCB4': 'Financeiro',
    'PETR4': 'Petroleo e Gas', 'PETR3': 'Petroleo e Gas', 'PRIO3': 'Petroleo e Gas',
    'RECV3': 'Petroleo e Gas', 'UGPA3': 'Petroleo e Gas', 'CSAN3': 'Petroleo e Gas',
    'VBBR3': 'Petroleo e Gas', 'ENAT3': 'Petroleo e Gas',
    'VALE3': 'Mineracao e Siderurgia', 'CSNA3': 'Mineracao e Siderurgia',
    'GGBR4': 'Mineracao e Siderurgia', 'USIM5': 'Mineracao e Siderurgia',
    'GOAU4': 'Mineracao e Siderurgia', 'CMIN3': 'Mineracao e Siderurgia',
    'ELET3': 'Energia Eletrica', 'ELET6': 'Energia Eletrica', 'EGIE3': 'Energia Eletrica',
    'EQTL3': 'Energia Eletrica', 'CMIG4': 'Energia Eletrica', 'CPFE3': 'Energia Eletrica',
    'TAEE11': 'Energia Eletrica', 'ENGI11': 'Energia Eletrica', 'NEOE3': 'Energia Eletrica',
    'CPLE6': 'Energia Eletrica', 'ENEV3': 'Energia Eletrica',
    'SBSP3': 'Saneamento', 'SAPR11': 'Saneamento', 'CSMG3': 'Saneamento',
    'HAPV3': 'Saude', 'RDOR3': 'Saude', 'RADL3': 'Saude', 'FLRY3': 'Saude',
    'HYPE3': 'Saude', 'ONCO3': 'Saude',
    'MGLU3': 'Varejo e Consumo', 'VIVA3': 'Varejo e Consumo', 'ARZZ3': 'Varejo e Consumo',
    'LREN3': 'Varejo e Consumo', 'PETZ3': 'Varejo e Consumo', 'NTCO3': 'Varejo e Consumo',
    'AZZA3': 'Varejo e Consumo', 'ASAI3': 'Varejo e Consumo', 'CRFB3': 'Varejo e Consumo',
    'PCAR3': 'Varejo e Consumo', 'ALPA4': 'Varejo e Consumo',
    'TOTS3': 'Tecnologia', 'LWSA3': 'Tecnologia', 'CASH3': 'Tecnologia',
    'ABEV3': 'Alimentos e Bebidas', 'JBSS3': 'Alimentos e Bebidas',
    'MRFG3': 'Alimentos e Bebidas', 'BEEF3': 'Alimentos e Bebidas',
    'BRFS3': 'Alimentos e Bebidas', 'SMTO3': 'Alimentos e Bebidas',
    'SLCE3': 'Alimentos e Bebidas',
    'CYRE3': 'Construcao e Imob.', 'EZTC3': 'Construcao e Imob.',
    'MRVE3': 'Construcao e Imob.', 'CURY3': 'Construcao e Imob.',
    'RENT3': 'Transporte e Logistica', 'CCRO3': 'Transporte e Logistica',
    'AZUL4': 'Transporte e Logistica', 'RAIL3': 'Transporte e Logistica',
    'VIVT3': 'Telecomunicacoes', 'TIMS3': 'Telecomunicacoes',
    'WEGE3': 'Industrial', 'EMBR3': 'Industrial',
    'SUZB3': 'Papel e Celulose', 'KLBN11': 'Papel e Celulose',
    'YDUQ3': 'Educacao', 'COGN3': 'Educacao',
    'MULT3': 'Shoppings', 'IGTI11': 'Shoppings', 'ALSO3': 'Shoppings',
    'GGPS3': 'Concessoes e Infra.', 'RAIZ4': 'Industrial',
    'BRAV3': 'Petroleo e Gas', 'RRRP3': 'Petroleo e Gas',
    'BRAP4': 'Mineracao e Siderurgia',
    'ALOS3': 'Shoppings', 'IGTI3': 'Shoppings',
    'AURE3': 'Energia Eletrica', 'CPLE3': 'Energia Eletrica',
    'ALUP11': 'Energia Eletrica', 'ISAE4': 'Energia Eletrica',
    'COCE5': 'Energia Eletrica', 'CLSC4': 'Energia Eletrica', 'TRPL4': 'Energia Eletrica',
    'ITSA4': 'Financeiro', 'BRBI11': 'Financeiro', 'BPAN4': 'Financeiro',
    'BRSR6': 'Financeiro',
    'BMOB3': 'Tecnologia', 'DESK3': 'Tecnologia', 'INTB3': 'Tecnologia',
    'POSI3': 'Tecnologia', 'LWSA3': 'Tecnologia',
    'MATD3': 'Saude', 'ANIM3': 'Saude', 'DASA3': 'Saude', 'QUAL3': 'Saude',
    'ODPV3': 'Saude', 'PNVL3': 'Saude',
    'MLAS3': 'Varejo e Consumo', 'SMFT3': 'Varejo e Consumo',
    'CAML3': 'Alimentos e Bebidas', 'MDIA3': 'Alimentos e Bebidas',
    'CVCB3': 'Varejo e Consumo', 'GRND3': 'Varejo e Consumo',
    'VULC3': 'Varejo e Consumo',
    'LAVV3': 'Construcao e Imob.', 'TRIS3': 'Construcao e Imob.',
    'DIRR3': 'Construcao e Imob.', 'EVEN3': 'Construcao e Imob.',
    'MDNE3': 'Construcao e Imob.', 'JHSF3': 'Construcao e Imob.',
    'PLPL3': 'Construcao e Imob.', 'TEND3': 'Construcao e Imob.',
    'RDNI3': 'Construcao e Imob.', 'MELK3': 'Construcao e Imob.',
    'HBSA3': 'Construcao e Imob.', 'TCSA3': 'Construcao e Imob.',
    'FRAS3': 'Industrial', 'TUPY3': 'Industrial', 'KEPL3': 'Industrial',
    'LEVE3': 'Industrial', 'SHUL4': 'Industrial', 'MYPK3': 'Industrial',
    'POMO4': 'Industrial', 'POMO3': 'Industrial', 'DXCO3': 'Industrial',
    'TGMA3': 'Transporte e Logistica', 'STBP3': 'Transporte e Logistica',
    'ECOR3': 'Transporte e Logistica', 'LOGN3': 'Transporte e Logistica',
    'SIMH3': 'Transporte e Logistica', 'MILS3': 'Transporte e Logistica',
    'PORT3': 'Transporte e Logistica', 'RAPT4': 'Transporte e Logistica',
    'RAPT3': 'Transporte e Logistica',
    'MOTV3': 'Varejo e Consumo', 'ORVR3': 'Varejo e Consumo',
    'SBFG3': 'Financeiro',
    'SRNA3': 'Industrial', 'LOGG3': 'Transporte e Logistica',
    'CSED3': 'Educacao', 'PASS5': 'Varejo e Consumo',
    'OPCT3': 'Saude', 'VLID3': 'Tecnologia',
    'BRKM5': 'Petroquimica', 'UNIP6': 'Petroquimica',
    'OFSA3': 'Saude', 'GMAT3': 'Construcao e Imob.',
    'SOJA3': 'Alimentos e Bebidas', 'PRNR3': 'Varejo e Consumo',
    'ZAMP3': 'Alimentos e Bebidas', 'TFCO4': 'Varejo e Consumo',
    'CSUD3': 'Industrial', 'BRST3': 'Industrial',
    'PGMN3': 'Construcao e Imob.', 'TTEN3': 'Industrial',
    'VIVA3': 'Varejo e Consumo', 'HBRE3': 'Construcao e Imob.',
    'MGEL4': 'Industrial', 'FBMC4': 'Financeiro',
    'TOKY3': 'Tecnologia', 'MBRF3': 'Alimentos e Bebidas',
    'NATU3': 'Varejo e Consumo',
    'ROXO34': 'Financeiro (US)', 'XPBR31': 'Financeiro (US)',
    'INBR32': 'Financeiro (US)', 'AURA33': 'Mineracao e Siderurgia',
    'STOC34': 'Financeiro (US)',
    'BOVA11': 'ETF - Ibovespa', 'DIVO11': 'ETF - Dividendos',
    'LVOL11': 'ETF - Low Vol', 'SMAL11': 'ETF - Small Cap',
    # ── Acoes listadas nos EUA (via BDR ou posicao direta) ──
    'AMZN US': 'Tecnologia (US)', 'AMZN': 'Tecnologia (US)',
    'META US': 'Tecnologia (US)', 'META': 'Tecnologia (US)',
    'MELI US': 'E-Commerce (US)', 'MELI': 'E-Commerce (US)',
    'NU US': 'Financeiro (US)', 'NU': 'Financeiro (US)',
    'STNE US': 'Financeiro (US)', 'STNE': 'Financeiro (US)',
    'INTR US': 'Financeiro (US)', 'INTR': 'Financeiro (US)',
    'XP US': 'Financeiro (US)', 'XP': 'Financeiro (US)',
    'DLO US': 'Financeiro (US)', 'DLO': 'Financeiro (US)',
    'VTEX US': 'Tecnologia (US)', 'VTEX': 'Tecnologia (US)',
    'PAGS US': 'Financeiro (US)', 'PAGS': 'Financeiro (US)',
    'GGAL US': 'Financeiro (US)', 'GGAL': 'Financeiro (US)',
    'BBAR US': 'Financeiro (US)', 'BBAR': 'Financeiro (US)',
    'GLOB US': 'Tecnologia (US)', 'GLOB': 'Tecnologia (US)',
    'MSFT US': 'Tecnologia (US)', 'GOOGL US': 'Tecnologia (US)',
    'AAPL US': 'Tecnologia (US)', 'NVDA US': 'Tecnologia (US)',
    'TSLA US': 'Automotivo (US)',
}

# Tickers que sao acoes (listadas fora do BR ou com formato nao-padrao) e NAO fundos
# Usado para evitar que aparecam como "Fundos nao explodidos"
US_STOCK_SUFFIXES = (" US",)  # Bloomberg-style tickers from CVM


def _is_stock_ticker(ticker: str) -> bool:
    """Determina se um ticker e uma acao (BR ou US) e nao um fundo/opcao/futuro."""
    tk = ticker.strip().upper()
    # Brazilian standard: 4 letters + 1-2 digits (PETR4, KLBN11, BOVA11, etc.)
    import re
    if re.match(r'^[A-Z]{4}\d{1,2}$', tk):
        return True
    # US stocks: XXXX US or similar Bloomberg-style
    if any(tk.endswith(sfx) for sfx in US_STOCK_SUFFIXES):
        return True
    # Explicit in SETOR_MAP as stock (not ETF-like)
    if tk in SETOR_MAP:
        return True
    return False


def _is_option_ticker(ticker: str) -> bool:
    """Determina se um ticker e uma opcao (ex: IBOVV136, PETRM25, etc.)."""
    tk = ticker.strip().upper()
    import re
    # Opcoes BR: 4 letras + 1 letra (serie) + digitos (strike) — ex: IBOVV136, PETRM25, VALEC30
    if re.match(r'^[A-Z]{4}[A-Z]\d+$', tk):
        return True
    return False


def classificar_setor(ticker: str) -> str:
    tk = ticker.strip().upper()
    if tk in SETOR_MAP:
        return SETOR_MAP[tk]
    # Opcoes
    if _is_option_ticker(tk):
        return 'Opcoes/Protecao'
    return 'Outros'

def _classificar_componente(nome: str, tipo: str) -> str:
    """Classificar componente do fundo em categoria broad."""
    if nome in COMPONENTE_CLASSE:
        return COMPONENTE_CLASSE[nome]
    if tipo == "Caixa":
        return "Caixa"
    if tipo == "RF":
        return "Renda Fixa"
    if tipo == "Fundo":
        if any(x in nome for x in ["RF", "Liq", "Apache"]):
            return "Caixa" if "Liq" in nome else "Renda Fixa"
        return "Fundos RV"
    if tipo == "Acao/ETF":
        return classificar_setor(nome)
    if tipo == "Futuro":
        return "Futuros" if "WIN" in nome else "Futuros (Outros)"
    if tipo in ("Opcao", "Opcao Futuro"):
        return "Opcoes/Protecao"
    return "Outros"

# ==============================================================================
# DATA: B3 IBOV / ETF COMPOSITION
# ==============================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_index_composition(index_code: str) -> dict:
    """Fetch index/ETF composition {ticker: weight%} from B3 API."""
    import requests as req
    try:
        payload = json.dumps({
            "language": "pt-br", "pageNumber": 1, "pageSize": 200,
            "index": index_code, "action": "3",
        })
        encoded = base64.b64encode(payload.encode()).decode()
        url = f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{encoded}"
        r = req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        data = r.json()
        comp = {}
        for item in data.get("results", []):
            cod = item.get("cod", "").strip()
            part_str = item.get("part", "0").replace(",", ".")
            try:
                part = float(part_str)
            except (ValueError, TypeError):
                part = 0.0
            if cod and part > 0:
                comp[cod] = part
        return comp
    except Exception:
        return {}

def fetch_ibov_composition() -> dict:
    return fetch_index_composition("IBOV")

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_etf_composition(ticker: str) -> dict:
    """Fetch ETF underlying composition via B3 index API."""
    idx = ETF_INDEX_MAP.get(ticker.upper(), "")
    if not idx or idx in ("S&P500", "CRYPTO", "IFIX"):
        return {}
    return fetch_index_composition(idx)

# ==============================================================================
# DATA: YFINANCE PRICES
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner="Buscando precos historicos...")
def fetch_prices(tickers_sa: tuple, start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    all_tickers = list(tickers_sa) + ["^BVSP"]
    df = yf.download(all_tickers, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df

# ==============================================================================
# MASTER CNPJ MAPPING (Feeder -> Master fund that holds the stocks in CVM)
# ==============================================================================
MASTER_CNPJ_MAP = {
    # Synta FIA II sub-fundos
    "15578434000140": "17162816000114",   # Atmos Institucional -> Atmos Master
    "28408121000196": "09143435000160",   # GTI Haifa FIA -> GTI Dimona Master
    "11961199000130": "20889133000178",   # Neo Navitas FIC -> Neo Navitas Master
    "42831345000137": "32812291000109",   # NV FC FIA -> Navi Institucional Master FIF
    "17157131000180": "27227810000131",   # Oceana Selection -> Oceana Selection Master
    "26956042000194": "18454944000102",   # Oceana Valor 30 -> Oceana Valor Master
    "49984812000108": "38251507000190",   # Organon Institucional -> Organon Master FIA
    "13455174000190": "13455136000138",   # Santander Dividendos CIC -> Santander Div FI
    "17898543000170": None,               # BNY ARX Liquidez RF -> RF, nao explode
    "16565084000140": "16565084000140",   # SPX Apache FIA -> ele mesmo
    # Synta FIA sub-fundos
    "53827819000193": "51752977000104",   # Absolute Pace FIC FIM -> Absolute Pace Master FIF MM
    "51427627000164": "17162816000114",   # Atmos Institucional S -> Atmos Master (mesmo)
    "52070019000108": "52070476000100",   # Real Investor FIC -> Real Investor Master
    "40226121000170": "39344972000139",   # Perfin Infra Equity FIC -> Perfin Infra Master
    "41632880000104": "15831948000166",   # SPX Falcon Inst -> SPX Falcon Master
    "39346123000114": "27389566000103",   # Tarpon GT Institucional -> Tarpon GT Master
}

# ==============================================================================
# DATA: SUB-FUND POSITIONS (from carteira_rv parquets + CVM BLC_4 fallback)
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner="Carregando posicoes dos sub-fundos...")
def load_subfund_positions() -> pd.DataFrame:
    """Load sub-fund stock positions from multiple sources, keeping most recent per fund.

    Priority order (all are checked, most recent date wins per fund):
      1. posicoes_consolidado.parquet (pre-merged XML+CVM data — may use master CNPJs)
      2. posicoes_xml.parquet (BNY Mellon XMLs — uses master CNPJs)
      3. posicoes_cvm.parquet (CVM downloads — uses master CNPJs)
      4. CVM BLC_4 cache parquets (oldest fallback)

    All sources apply master→feeder CNPJ remapping via MASTER_CNPJ_MAP.
    """
    frames = []

    # Build master→feeder mapping (used by all sources)
    master_to_feeders = {}  # master_cnpj -> [feeder_cnpj, ...]
    for feeder, master in MASTER_CNPJ_MAP.items():
        if master and master != feeder:
            master_to_feeders.setdefault(master, []).append(feeder)

    def _remap_master_to_feeder(df_src):
        """Create copies of master-CNPJ rows with feeder CNPJs."""
        remapped = []
        for master_cnpj, feeders in master_to_feeders.items():
            master_data = df_src[df_src["cnpj_fundo"] == master_cnpj]
            if master_data.empty:
                continue
            for feeder_cnpj in feeders:
                df_copy = master_data.copy()
                df_copy["cnpj_fundo"] = feeder_cnpj
                remapped.append(df_copy)
        # Self-mapped entries (feeder == master, e.g. SPX Apache)
        for feeder, master in MASTER_CNPJ_MAP.items():
            if master == feeder:
                direct = df_src[df_src["cnpj_fundo"] == feeder]
                if not direct.empty:
                    remapped.append(direct)
        return remapped

    # --- Source 1: posicoes_consolidado.parquet ---
    parquet_path = os.path.join(CARTEIRA_RV_DATA, "posicoes_consolidado.parquet")
    if not os.path.exists(parquet_path):
        parquet_path = os.path.join(DATA_DIR, "posicoes_consolidado.parquet")
    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
        df["data"] = pd.to_datetime(df["data"])
        if "setor" in df.columns:
            df["setor"] = df["ativo"].apply(classificar_setor)
        frames.append(df)
        # Remap master→feeder in consolidado (it may contain master CNPJs)
        remapped = _remap_master_to_feeder(df)
        if remapped:
            frames.append(pd.concat(remapped, ignore_index=True))

    # --- Source 2 & 3: posicoes_xml.parquet and posicoes_cvm.parquet ---
    for extra_file in ["posicoes_xml.parquet", "posicoes_cvm.parquet"]:
        extra_path = os.path.join(CARTEIRA_RV_DATA, extra_file)
        if not os.path.exists(extra_path):
            extra_path = os.path.join(DATA_DIR, extra_file)  # Cloud fallback
        if not os.path.exists(extra_path):
            continue
        try:
            df_extra = pd.read_parquet(extra_path)
            df_extra["data"] = pd.to_datetime(df_extra["data"])
            if "setor" in df_extra.columns:
                df_extra["setor"] = df_extra["ativo"].apply(classificar_setor)
            # Remap master CNPJs to feeder CNPJs
            remapped = _remap_master_to_feeder(df_extra)
            if remapped:
                frames.append(pd.concat(remapped, ignore_index=True))
        except Exception:
            pass

    # --- Source 4: CVM BLC_4 cache (oldest fallback) ---
    existing_cnpjs = set()
    if frames:
        existing_cnpjs = set(pd.concat(frames, ignore_index=True)["cnpj_fundo"].unique())

    cvm_rows = _load_cvm_blc4_positions(existing_cnpjs)
    if cvm_rows:
        df_cvm = pd.DataFrame(cvm_rows)
        frames.append(df_cvm)

    if not frames:
        return pd.DataFrame(columns=["cnpj_fundo", "data", "ativo", "valor", "pl", "pct_pl", "setor", "fonte"])

    # Merge all sources — for each fund, keep only the MOST RECENT date across all sources
    result = pd.concat(frames, ignore_index=True)
    # Find latest date per fund
    latest_per_fund = result.groupby("cnpj_fundo")["data"].max().reset_index()
    latest_per_fund.columns = ["cnpj_fundo", "latest_data"]
    result = result.merge(latest_per_fund, on="cnpj_fundo")
    result = result[result["data"] == result["latest_data"]].drop(columns=["latest_data"])
    result = result.drop_duplicates(subset=["cnpj_fundo", "data", "ativo"], keep="last")
    return result


@st.cache_data(ttl=3600, show_spinner="Carregando historico de composicoes...")
def load_subfund_positions_all() -> pd.DataFrame:
    """Load ALL historical sub-fund stock positions (all dates, not just latest).

    Same sources as load_subfund_positions() but keeps all historical dates.
    Used for historical sector evolution charts where we need the closest
    composition snapshot for each day.
    """
    frames = []

    # Build master→feeder mapping (used by all sources)
    master_to_feeders = {}
    for feeder, master in MASTER_CNPJ_MAP.items():
        if master and master != feeder:
            master_to_feeders.setdefault(master, []).append(feeder)

    def _remap(df_src):
        """Create copies of master-CNPJ rows with feeder CNPJs."""
        remapped = []
        for master_cnpj, feeders in master_to_feeders.items():
            master_data = df_src[df_src["cnpj_fundo"] == master_cnpj]
            if master_data.empty:
                continue
            for feeder_cnpj in feeders:
                df_copy = master_data.copy()
                df_copy["cnpj_fundo"] = feeder_cnpj
                remapped.append(df_copy)
        for feeder, master in MASTER_CNPJ_MAP.items():
            if master == feeder:
                direct = df_src[df_src["cnpj_fundo"] == feeder]
                if not direct.empty:
                    remapped.append(direct)
        return remapped

    # --- Source 1: posicoes_consolidado.parquet ---
    parquet_path = os.path.join(CARTEIRA_RV_DATA, "posicoes_consolidado.parquet")
    if not os.path.exists(parquet_path):
        parquet_path = os.path.join(DATA_DIR, "posicoes_consolidado.parquet")
    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
        df["data"] = pd.to_datetime(df["data"])
        if "setor" in df.columns:
            df["setor"] = df["ativo"].apply(classificar_setor)
        frames.append(df)
        # Remap master→feeder in consolidado too
        remapped = _remap(df)
        if remapped:
            frames.append(pd.concat(remapped, ignore_index=True))

    # --- Source 2 & 3: posicoes_xml.parquet and posicoes_cvm.parquet ---
    for extra_file in ["posicoes_xml.parquet", "posicoes_cvm.parquet"]:
        extra_path = os.path.join(CARTEIRA_RV_DATA, extra_file)
        if not os.path.exists(extra_path):
            extra_path = os.path.join(DATA_DIR, extra_file)  # Cloud fallback
        if not os.path.exists(extra_path):
            continue
        try:
            df_extra = pd.read_parquet(extra_path)
            df_extra["data"] = pd.to_datetime(df_extra["data"])
            if "setor" in df_extra.columns:
                df_extra["setor"] = df_extra["ativo"].apply(classificar_setor)
            remapped = _remap(df_extra)
            if remapped:
                frames.append(pd.concat(remapped, ignore_index=True))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame(columns=["cnpj_fundo", "data", "ativo", "valor", "pl", "pct_pl", "setor", "fonte"])

    result = pd.concat(frames, ignore_index=True)
    # Deduplicate: for same (cnpj, date, ativo), keep last source
    result = result.drop_duplicates(subset=["cnpj_fundo", "data", "ativo"], keep="last")
    return result


def _get_subfund_snapshot(subfund_positions_all: pd.DataFrame, cnpj: str,
                          ref_date: pd.Timestamp) -> pd.DataFrame:
    """Get the closest composition snapshot for a fund at or before ref_date.

    Returns the DataFrame of positions for that fund on the closest available date.
    """
    df_fund = subfund_positions_all[subfund_positions_all["cnpj_fundo"] == cnpj]
    if df_fund.empty:
        return pd.DataFrame()
    # Find closest date <= ref_date
    available_dates = df_fund["data"].unique()
    valid_dates = available_dates[available_dates <= ref_date]
    if len(valid_dates) == 0:
        # No date before ref_date — use earliest available
        valid_dates = available_dates
    closest_date = valid_dates.max()
    return df_fund[df_fund["data"] == closest_date]


def _load_cvm_blc4_positions(existing_cnpjs: set) -> list:
    """Load stock positions from CVM BLC_4 cache for funds not in existing data.
    Uses MASTER_CNPJ_MAP to map feeder CNPJs to their master fund CNPJs."""
    cache_dir = CARTEIRA_RV_CACHE
    if not os.path.isdir(cache_dir):
        return []

    # Determine which master CNPJs we need to look up
    needed = {}  # master_cnpj -> [feeder_cnpj1, feeder_cnpj2, ...]
    for feeder_cnpj, master_cnpj in MASTER_CNPJ_MAP.items():
        if master_cnpj is None:
            continue
        if feeder_cnpj in existing_cnpjs:
            continue  # already have data from parquet
        if master_cnpj not in needed:
            needed[master_cnpj] = []
        needed[master_cnpj].append(feeder_cnpj)

    if not needed:
        return []

    # Find BLC_4 cache files, try from most recent backward
    blc4_files = sorted(glob.glob(os.path.join(cache_dir, "cvm_blc4_*.parquet")), reverse=True)
    if not blc4_files:
        return []

    # Format master CNPJs as xx.xxx.xxx/xxxx-xx for matching CVM format
    def format_cnpj(c):
        c = c.zfill(14)
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}"

    master_formatted = {format_cnpj(m): m for m in needed.keys()}
    rows = []
    found_masters = set()

    # Also load PL data for percentage calculation
    pl_data = {}

    for blc4_file in blc4_files:
        if len(found_masters) == len(needed):
            break  # All masters found

        try:
            df_blc = pd.read_parquet(blc4_file)
        except Exception:
            continue

        # Determine CNPJ column name (changed between CVM format versions)
        cnpj_col = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in df_blc.columns else "CNPJ_FUNDO"

        # Filter for stock-like assets
        if "TP_APLIC" not in df_blc.columns or "CD_ATIVO" not in df_blc.columns:
            continue

        # Match: Acoes, Ações, Acoes (various accents)
        mask_stocks = df_blc["TP_APLIC"].str.contains(r"(?:A.{1,3}es|Brazilian Depository)", case=False, na=False)
        mask_value = df_blc["VL_MERC_POS_FINAL"].fillna(0) > 0
        df_stocks = df_blc[mask_stocks & mask_value].copy()

        if df_stocks.empty:
            continue

        # Extract month from filename for date
        fname = os.path.basename(blc4_file)
        month_str = fname.replace("cvm_blc4_", "").replace(".parquet", "")
        try:
            ref_date = pd.Timestamp(f"{month_str[:4]}-{month_str[4:6]}-28")
        except Exception:
            continue

        # Try to load PL for this month
        pl_file = os.path.join(cache_dir, f"cvm_pl_{month_str}.parquet")
        if os.path.exists(pl_file) and month_str not in pl_data:
            try:
                df_pl = pd.read_parquet(pl_file)
                pl_cnpj_col = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in df_pl.columns else "CNPJ_FUNDO"
                for _, row in df_pl.iterrows():
                    cnpj_val = str(row.get(pl_cnpj_col, ""))
                    vl_pl = row.get("VL_PATRIM_LIQ", 0)
                    if cnpj_val and vl_pl and vl_pl > 0:
                        pl_data[(cnpj_val, month_str)] = vl_pl
            except Exception:
                pass

        for fmt_cnpj, raw_master in master_formatted.items():
            if raw_master in found_masters:
                continue

            df_fund = df_stocks[df_stocks[cnpj_col] == fmt_cnpj]
            if df_fund.empty:
                continue

            found_masters.add(raw_master)
            feeder_cnpjs = needed[raw_master]

            # Get PL for this master
            fund_pl = pl_data.get((fmt_cnpj, month_str), 0)
            if fund_pl <= 0:
                # Estimate PL from sum of positions (rough)
                fund_pl = df_fund["VL_MERC_POS_FINAL"].sum() * 1.05  # +5% for non-stock assets

            for _, row in df_fund.iterrows():
                ticker = str(row.get("CD_ATIVO", "")).strip()
                valor = float(row.get("VL_MERC_POS_FINAL", 0))
                if not ticker or valor <= 0:
                    continue
                pct = (valor / fund_pl * 100) if fund_pl > 0 else 0

                # Add row for EACH feeder that maps to this master
                for feeder_cnpj in feeder_cnpjs:
                    rows.append({
                        "cnpj_fundo": feeder_cnpj,
                        "data": ref_date,
                        "ativo": ticker,
                        "valor": valor,
                        "pl": fund_pl,
                        "pct_pl": pct,
                        "setor": classificar_setor(ticker),
                        "fonte": "CVM",
                    })

    return rows

# ==============================================================================
# COMPUTATION: DAILY CUMULATIVE ATTRIBUTION (IBOV) — with weight drift
# ==============================================================================
def compute_ibov_daily_attribution(composition: dict, df_prices: pd.DataFrame):
    tickers = sorted(composition.keys())
    col_map = {}
    for tk in tickers:
        sa = f"{tk}.SA"
        if sa in df_prices.columns:
            col_map[tk] = sa
    if not col_map or "^BVSP" not in df_prices.columns:
        return pd.DataFrame(), pd.DataFrame()
    ibov_prices = df_prices["^BVSP"].dropna()
    if len(ibov_prices) < 2:
        return pd.DataFrame(), pd.DataFrame()
    ibov_ret = ibov_prices.pct_change(fill_method=None)
    common_dates = ibov_ret.dropna().index
    ticker_returns = {}
    for tk in col_map:
        prices_tk = df_prices[col_map[tk]].reindex(common_dates)
        ticker_returns[tk] = prices_tk.pct_change(fill_method=None)
    total_weight = sum(composition[tk] for tk in col_map)
    current_weights = {tk: composition[tk] / total_weight for tk in col_map}
    daily_contribs = {tk: pd.Series(0.0, index=common_dates) for tk in col_map}
    for i in range(1, len(common_dates)):
        ibov_r = ibov_ret.iloc[i]
        if pd.isna(ibov_r):
            ibov_r = 0.0
        for tk in col_map:
            r = ticker_returns[tk].iloc[i]
            if pd.isna(r):
                r = 0.0
            daily_contribs[tk].iloc[i] = current_weights.get(tk, 0) * r
        if ibov_r != -1:
            for tk in col_map:
                r = ticker_returns[tk].iloc[i]
                if pd.isna(r):
                    r = 0.0
                current_weights[tk] = current_weights.get(tk, 0) * (1 + r) / (1 + ibov_r)
    df_daily = pd.DataFrame(daily_contribs, index=common_dates)
    cumulative_contrib = df_daily.iloc[1:].sum()
    rows = []
    for tk in col_map:
        prices_tk = df_prices[col_map[tk]].reindex(common_dates).dropna()
        ret_pct = (prices_tk.iloc[-1] / prices_tk.iloc[0] - 1) * 100 if len(prices_tk) >= 2 else 0.0
        rows.append({
            "ticker": tk, "setor": classificar_setor(tk),
            "weight_pct": composition[tk], "return_pct": ret_pct,
            "contribution_pct": cumulative_contrib.get(tk, 0) * 100,
        })
    df_attr = pd.DataFrame(rows).sort_values("contribution_pct", ascending=False)
    return df_attr, df_daily

def aggregate_by_sector(df_attr: pd.DataFrame) -> pd.DataFrame:
    if df_attr.empty:
        return pd.DataFrame()
    grouped = df_attr.groupby("setor").agg(
        weight_pct=("weight_pct", "sum"), contribution_pct=("contribution_pct", "sum"),
        n_stocks=("ticker", "count"),
    ).reset_index()
    grouped["sector_return_pct"] = np.where(
        grouped["weight_pct"] != 0, grouped["contribution_pct"] / grouped["weight_pct"] * 100, 0)
    return grouped.sort_values("contribution_pct", ascending=False)

# ==============================================================================
# DATA: PARSE SYNTA XML
# ==============================================================================
def _find_synta_xml(date_str: str, xml_prefix: str):
    folder = os.path.join(XML_BASE, date_str)
    if not os.path.isdir(folder):
        return None
    files = glob.glob(os.path.join(folder, f"{xml_prefix}_*"))
    return files[0] if files else None

def parse_synta_xml(filepath: str) -> dict:
    tree = ET.parse(filepath)
    root = tree.getroot()
    fundo = root.find("fundo")
    if fundo is None:
        return {}
    header = fundo.find("header")
    result = {
        "cnpj": header.findtext("cnpj", ""),
        "nome": header.findtext("nome", ""),
        "dtposicao": header.findtext("dtposicao", ""),
        "patliq": float(header.findtext("patliq", "0") or 0),
        "valorcota": float(header.findtext("valorcota", "0") or 0),
        "quantidade_cotas": float(header.findtext("quantidade", "0") or 0),
        "posicoes": [],
    }
    pl = result["patliq"]
    if pl <= 0:
        return result
    # RF — agrupar todos titulos publicos; calcular PU medio ponderado para retorno
    rf_valor = 0.0
    rf_qtd = 0.0
    for tp in fundo.findall("titpublico"):
        vf = float(tp.findtext("valorfindisp", "0") or 0)
        qtd = float(tp.findtext("qtdisponivel", "0") or 0)
        rf_valor += vf
        rf_qtd += qtd
    if rf_valor > 0:
        rf_pu = rf_valor / rf_qtd if rf_qtd > 0 else 0
        result["posicoes"].append({"componente": "Renda Fixa (LFT)", "tipo": "RF", "valor": rf_valor,
                                    "peso_pct": rf_valor / pl * 100, "pu": rf_pu, "qtd": rf_qtd, "vlajuste": 0})
    # Acoes — agregar por codigo, guardar PU e QTD total
    acoes_map = {}
    for ac in fundo.findall("acoes"):
        cod = ac.findtext("codativo", "")
        classe = ac.findtext("classeoperacao", "C")
        vf_disp = float(ac.findtext("valorfindisp", "0") or 0)
        qtd_gar = float(ac.findtext("qtgarantia", "0") or 0)
        pu = float(ac.findtext("puposicao", "0") or 0)
        qtd_disp = float(ac.findtext("qtdisponivel", "0") or 0)
        if cod not in acoes_map:
            acoes_map[cod] = {"valor": 0.0, "qtd": 0.0, "pu": pu}
        if classe == "C":
            acoes_map[cod]["valor"] += vf_disp
            acoes_map[cod]["qtd"] += qtd_disp
        else:
            acoes_map[cod]["valor"] += qtd_gar * pu
            acoes_map[cod]["qtd"] += qtd_gar
    for cod, info in acoes_map.items():
        if info["valor"] > 0:
            result["posicoes"].append({"componente": cod, "tipo": "Acao/ETF", "valor": info["valor"],
                                        "peso_pct": info["valor"] / pl * 100, "pu": info["pu"], "qtd": info["qtd"], "vlajuste": 0})
    # Futuros — usar vlajuste (ajuste diario = P&L real), nao vltotalpos
    for fut in fundo.findall("futuros"):
        ativo = fut.findtext("ativo", "")
        serie = fut.findtext("serie", "")
        vl = float(fut.findtext("vltotalpos", "0") or 0)
        vlaj = float(fut.findtext("vlajuste", "0") or 0)
        result["posicoes"].append({"componente": f"FUT {ativo} {serie}", "tipo": "Futuro", "valor": vl,
                                    "peso_pct": vl / pl * 100, "pu": 0, "qtd": 0, "vlajuste": vlaj})
    # Opcoes
    for op in fundo.findall("opcoes"):
        cod = op.findtext("codativo", "")
        vf = float(op.findtext("valorfinanceiro", "0") or 0)
        pu = float(op.findtext("puposicao", "0") or 0)
        qtd = float(op.findtext("qtdisponivel", "0") or 0)
        if vf != 0:
            result["posicoes"].append({"componente": f"OPC {cod}", "tipo": "Opcao", "valor": vf,
                                        "peso_pct": vf / pl * 100, "pu": pu, "qtd": qtd, "vlajuste": 0})
    for od in fundo.findall("opcoesderiv"):
        serie = od.findtext("serie", "")
        vf = float(od.findtext("valorfinanceiro", "0") or 0)
        pu = float(od.findtext("puposicao", "0") or 0)
        qtd = float(od.findtext("qtd", "0") or 0)
        if vf != 0:
            result["posicoes"].append({"componente": f"OPFUT {serie}", "tipo": "Opcao Futuro", "valor": vf,
                                        "peso_pct": vf / pl * 100, "pu": pu, "qtd": qtd, "vlajuste": 0})
    # Caixa
    for cx in fundo.findall("caixa"):
        saldo = float(cx.findtext("saldo", "0") or 0)
        if saldo != 0:
            result["posicoes"].append({"componente": "Caixa", "tipo": "Caixa", "valor": saldo,
                                        "peso_pct": saldo / pl * 100, "pu": 0, "qtd": 0, "vlajuste": 0})
    # Cotas de fundos
    for cota in fundo.findall("cotas"):
        cnpj_f = cota.findtext("cnpjfundo", "")
        qtd = float(cota.findtext("qtdisponivel", "0") or 0)
        pu = float(cota.findtext("puposicao", "0") or 0)
        valor = qtd * pu
        nome = SUBFUNDO_NAMES.get(cnpj_f, f"Fundo {cnpj_f}")
        result["posicoes"].append({"componente": nome, "tipo": "Fundo", "cnpj": cnpj_f, "valor": valor,
                                    "peso_pct": valor / pl * 100, "qtd_cotas": qtd, "pu": pu, "qtd": qtd, "vlajuste": 0})
    return result

@st.cache_data(ttl=600, show_spinner="Carregando posicoes do fundo...")
def load_synta_timeseries(fundo_key: str, start_str: str, end_str: str) -> pd.DataFrame:
    config = FUNDOS_CONFIG[fundo_key]
    prefix = config["xml_prefix"]
    start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
    fetch_start = start_dt - timedelta(days=10)

    # --- Cloud mode: read from pre-exported parquet ---
    if not HAS_LOCAL_XML and HAS_PARQUET_DATA:
        safe_name = fundo_key.lower().replace(" ", "_")
        parquet_path = os.path.join(DATA_DIR, f"timeseries_{safe_name}.parquet")
        if os.path.exists(parquet_path):
            df = pd.read_parquet(parquet_path)
            df["data"] = pd.to_datetime(df["data"])
            df = df[(df["data"].dt.date >= fetch_start) & (df["data"].dt.date <= end_dt)]
            return df
        return pd.DataFrame()

    # --- Local mode: parse XMLs ---
    if not os.path.isdir(XML_BASE):
        return pd.DataFrame()
    all_rows = []
    for folder_name in sorted(os.listdir(XML_BASE)):
        try:
            folder_date = datetime.strptime(folder_name, "%Y%m%d").date()
        except ValueError:
            continue
        if folder_date < fetch_start or folder_date > end_dt:
            continue
        xml_path = _find_synta_xml(folder_name, prefix)
        if not xml_path:
            continue
        parsed = parse_synta_xml(xml_path)
        if not parsed or not parsed.get("posicoes"):
            continue
        for pos in parsed["posicoes"]:
            all_rows.append({
                "data": pd.Timestamp(folder_date), "componente": pos["componente"],
                "tipo": pos["tipo"], "valor": pos["valor"], "peso_pct": pos["peso_pct"],
                "patliq": parsed["patliq"], "valorcota": parsed["valorcota"],
                "pu": pos.get("pu", 0), "vlajuste": pos.get("vlajuste", 0),
            })
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()

# ==============================================================================
# COMPUTATION: SYNTA ATTRIBUTION
# ==============================================================================
def compute_synta_attribution(df_ts: pd.DataFrame, period_start: str = None) -> pd.DataFrame:
    """Atribuicao de performance por componente usando metodo peso x retorno.

    Para cada dia t:
      - Ativos normais (acoes, RF, fundos): contrib_i(t) = peso_i(t-1) * retorno_pu_i(t)
        onde retorno_pu = PU(t)/PU(t-1) - 1
      - Futuros: contrib_i(t) = vlajuste_i(t) / PL(t-1)
      - Opcoes/Caixa: contrib_i(t) = delta_valor_i(t) / PL(t-1) (fallback)
    Ao final, escala proporcional para fechar com retorno real da cota.
    """
    if df_ts.empty:
        return pd.DataFrame()
    dates = sorted(df_ts["data"].unique())
    if len(dates) < 2:
        return pd.DataFrame()

    # Series de PL e cota
    meta = df_ts.drop_duplicates("data").set_index("data").sort_index()
    pl_series = meta["patliq"]
    cota_series = meta["valorcota"]

    # Determinar base_date e retorno total do fundo
    base_date = None
    if period_start:
        ps = pd.Timestamp(period_start)
        dates_before = cota_series.index[cota_series.index < ps]
        if len(dates_before) > 0:
            base_date = dates_before[-1]
    if base_date is not None:
        base_cota = cota_series.loc[base_date]
    else:
        base_cota = cota_series.iloc[0]
        base_date = cota_series.index[0]
    ret_total = (cota_series.iloc[-1] / base_cota - 1) * 100

    # Filtrar dados a partir do base_date
    df_period = df_ts[df_ts["data"] >= base_date].copy()
    period_dates = sorted(df_period["data"].unique())
    if len(period_dates) < 2:
        return pd.DataFrame()

    # Pivotar valor, PU e vlajuste por componente x data
    pivot_val = df_period.pivot_table(index="data", columns="componente", values="valor", aggfunc="sum").fillna(0).sort_index()
    pivot_pu = df_period.pivot_table(index="data", columns="componente", values="pu", aggfunc="first").fillna(0).sort_index()
    pivot_vlaj = df_period.pivot_table(index="data", columns="componente", values="vlajuste", aggfunc="sum").fillna(0).sort_index()
    pl_period = pl_series.loc[pl_series.index >= base_date].sort_index()

    # Tipo de cada componente
    tipo_map = df_period.drop_duplicates("componente").set_index("componente")["tipo"]

    # Calcular contribuicao diaria para cada componente
    components = pivot_val.columns.tolist()
    cum_contrib = pd.Series(0.0, index=components)

    for i in range(1, len(period_dates)):
        dt_prev = period_dates[i - 1]
        dt_curr = period_dates[i]
        pl_prev = pl_period.loc[dt_prev]
        if pl_prev <= 0:
            continue

        for comp in components:
            tipo = tipo_map.get(comp, "")
            val_prev = pivot_val.loc[dt_prev, comp] if comp in pivot_val.columns else 0
            val_curr = pivot_val.loc[dt_curr, comp] if comp in pivot_val.columns else 0
            peso_prev = val_prev / pl_prev  # peso no inicio do dia

            if tipo == "Futuro":
                # Futuros: contribuicao = vlajuste / PL anterior
                vlaj = pivot_vlaj.loc[dt_curr, comp] if comp in pivot_vlaj.columns else 0
                contrib = vlaj / pl_prev
            elif tipo in ("Acao/ETF", "RF", "Fundo"):
                # Ativos com PU: contribuicao = peso(t-1) * retorno_pu(t)
                pu_prev = pivot_pu.loc[dt_prev, comp] if comp in pivot_pu.columns else 0
                pu_curr = pivot_pu.loc[dt_curr, comp] if comp in pivot_pu.columns else 0
                if pu_prev > 0 and pu_curr > 0:
                    ret_pu = (pu_curr / pu_prev) - 1
                    contrib = peso_prev * ret_pu
                else:
                    # Fallback: delta valor / PL
                    contrib = (val_curr - val_prev) / pl_prev if pl_prev > 0 else 0
            else:
                # Opcoes, Caixa, etc: delta valor / PL (fallback)
                contrib = (val_curr - val_prev) / pl_prev if pl_prev > 0 else 0

            cum_contrib[comp] += contrib

    cum_contrib = cum_contrib * 100  # converter para percentual

    # Escalar proporcionalmente para fechar com retorno real da cota
    sum_contrib = cum_contrib.sum()
    if abs(sum_contrib) > 0.001 and abs(ret_total) > 0.001:
        scale = ret_total / sum_contrib
        cum_contrib = cum_contrib * scale

    # Pesos inicio (base_date) e fim (ultimo dia)
    first_date = period_dates[0]
    last_date = period_dates[-1]
    pl_first = pl_period.loc[first_date]
    pl_last = pl_period.loc[last_date]
    weights_start = pivot_val.loc[first_date] / pl_first * 100 if pl_first > 0 else pivot_val.loc[first_date] * 0
    weights_end = pivot_val.loc[last_date] / pl_last * 100 if pl_last > 0 else pivot_val.loc[last_date] * 0

    rows = []
    for comp in components:
        rows.append({"componente": comp, "tipo": tipo_map.get(comp, ""),
                      "peso_inicio": weights_start.get(comp, 0), "peso_fim": weights_end.get(comp, 0),
                      "contribution_pct": cum_contrib.get(comp, 0)})
    df_attr = pd.DataFrame(rows).sort_values("contribution_pct", ascending=False)
    df_attr["retorno_total_fundo"] = ret_total
    return df_attr

# ==============================================================================
# COMPUTATION: BRINSON-FACHLER
# ==============================================================================
def compute_brinson_fachler(fund_w, fund_r, bench_w, bench_r, bench_total):
    all_sectors = sorted(set(list(fund_w.keys()) + list(bench_w.keys())))
    rows = []
    for s in all_sectors:
        w_p, w_b = fund_w.get(s, 0) / 100, bench_w.get(s, 0) / 100
        r_p, r_b = fund_r.get(s, 0) / 100, bench_r.get(s, 0) / 100
        r_bench = bench_total / 100
        alloc = (w_p - w_b) * (r_b - r_bench)
        selec = w_b * (r_p - r_b)
        inter = (w_p - w_b) * (r_p - r_b)
        rows.append({"setor": s, "peso_fundo": w_p * 100, "peso_bench": w_b * 100,
                      "ret_fundo": r_p * 100, "ret_bench": r_b * 100,
                      "alocacao": alloc * 100, "selecao": selec * 100,
                      "interacao": inter * 100, "total": (alloc + selec + inter) * 100})
    return pd.DataFrame(rows).sort_values("total", ascending=False)

# ==============================================================================
# EXPLOSION: Sub-fund + ETF -> individual stocks
# ==============================================================================
@st.cache_data(ttl=600, show_spinner="Explodindo carteira em acoes individuais...")
def explode_fund_to_stocks(fundo_key: str, ref_date_str: str) -> pd.DataFrame:
    """Explode a Synta fund into individual stock exposures.

    For each component:
    - Sub-funds (Fundo type): look up stock positions from CVM/XML data
    - ETFs (BOVA11 etc): decompose via B3 index API
    - Direct stocks: keep as-is
    - RF/Caixa/Futuros/Opcoes: classify but don't explode
    """
    config = FUNDOS_CONFIG[fundo_key]
    prefix = config["xml_prefix"]
    ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d").date()

    parsed = None
    # --- Cloud mode: reconstruct positions from parquet ---
    if not HAS_LOCAL_XML and HAS_PARQUET_DATA:
        safe_name = fundo_key.lower().replace(" ", "_")
        parquet_path = os.path.join(DATA_DIR, f"timeseries_{safe_name}.parquet")
        if os.path.exists(parquet_path):
            df_pq = pd.read_parquet(parquet_path)
            df_pq["data"] = pd.to_datetime(df_pq["data"])
            df_pq = df_pq[df_pq["data"].dt.date <= ref_dt]
            if not df_pq.empty:
                latest_date = df_pq["data"].max()
                df_snap = df_pq[df_pq["data"] == latest_date]
                pl = df_snap["patliq"].iloc[0]
                posicoes = []
                for _, row in df_snap.iterrows():
                    pos = {
                        "componente": row["componente"], "tipo": row["tipo"],
                        "valor": row["valor"], "peso_pct": row["peso_pct"],
                        "pu": row.get("pu", 0),
                    }
                    if "cnpj" in row and pd.notna(row.get("cnpj")):
                        pos["cnpj"] = row["cnpj"]
                    posicoes.append(pos)
                parsed = {"patliq": pl, "posicoes": posicoes}

    # --- Local mode: parse XML ---
    if parsed is None and HAS_LOCAL_XML:
        xml_path = None
        for folder_name in sorted(os.listdir(XML_BASE), reverse=True):
            try:
                folder_date = datetime.strptime(folder_name, "%Y%m%d").date()
            except ValueError:
                continue
            if folder_date <= ref_dt:
                xml_path = _find_synta_xml(folder_name, prefix)
                if xml_path:
                    break
        if xml_path:
            parsed = parse_synta_xml(xml_path)

    if not parsed or not parsed.get("posicoes"):
        return pd.DataFrame()

    pl = parsed["patliq"]
    subfund_positions = load_subfund_positions()

    exposures = []

    for pos in parsed["posicoes"]:
        comp = pos["componente"]
        tipo = pos["tipo"]
        peso_no_fundo = pos["peso_pct"]
        classe = _classificar_componente(comp, tipo)

        if tipo == "Fundo":
            cnpj_sub = pos.get("cnpj", "")
            nome_sub = comp

            # Try to find stock positions for this sub-fund
            if cnpj_sub and not subfund_positions.empty:
                df_sub = subfund_positions[subfund_positions["cnpj_fundo"] == cnpj_sub]
                if not df_sub.empty:
                    latest = df_sub["data"].max()
                    df_snap = df_sub[df_sub["data"] == latest]

                    # Normalize: if sum of pct_pl > 100%, scale down to 100%
                    # (handles leveraged funds or CVM data with guarantees)
                    total_pct = df_snap["pct_pl"].sum()
                    scale_factor = 100.0 / total_pct if total_pct > 100 else 1.0

                    for _, row in df_snap.iterrows():
                        ticker = row["ativo"]
                        pct_in_sub = row["pct_pl"] * scale_factor
                        expo = peso_no_fundo / 100 * pct_in_sub

                        # Check if this is an ETF that needs further explosion
                        if ticker in ETF_INDEX_MAP:
                            etf_comp = fetch_etf_composition(ticker)
                            if etf_comp:
                                for etf_tk, etf_w in etf_comp.items():
                                    expo_etf = expo / 100 * etf_w
                                    exposures.append({
                                        "ativo": etf_tk, "setor": classificar_setor(etf_tk),
                                        "origem": f"{nome_sub} > {ticker}",
                                        "peso_componente": peso_no_fundo,
                                        "peso_no_subfundo": pct_in_sub,
                                        "exposicao_pct": expo_etf, "tipo_origem": "Fundo>ETF",
                                    })
                                continue

                        # Classify tipo_origem based on actual ticker type
                        if _is_option_ticker(ticker):
                            sub_tipo = "Opcao"
                        elif _is_stock_ticker(ticker):
                            sub_tipo = "Fundo"  # stock from sub-fund explosion
                        else:
                            sub_tipo = "Fundo"  # unknown — keep as fund exposure

                        exposures.append({
                            "ativo": ticker, "setor": classificar_setor(ticker),
                            "origem": nome_sub, "peso_componente": peso_no_fundo,
                            "peso_no_subfundo": pct_in_sub,
                            "exposicao_pct": expo, "tipo_origem": sub_tipo,
                        })
                    continue

            # No stock data found — keep as aggregate
            # Use classe-based tipo_origem so RF/Caixa funds are not counted as equity
            if classe in ("Caixa", "Renda Fixa"):
                tipo_agg = "RF"
            else:
                tipo_agg = tipo  # "Fundo" for equity funds without CVM data
            exposures.append({
                "ativo": comp, "setor": classe, "origem": "Direto",
                "peso_componente": peso_no_fundo, "peso_no_subfundo": 100,
                "exposicao_pct": peso_no_fundo, "tipo_origem": tipo_agg,
            })

        elif tipo == "Acao/ETF":
            ticker = comp
            if ticker in ETF_INDEX_MAP:
                etf_comp = fetch_etf_composition(ticker)
                if etf_comp:
                    for etf_tk, etf_w in etf_comp.items():
                        expo_etf = peso_no_fundo * etf_w / 100
                        exposures.append({
                            "ativo": etf_tk, "setor": classificar_setor(etf_tk),
                            "origem": f"{ticker} (ETF)", "peso_componente": peso_no_fundo,
                            "peso_no_subfundo": etf_w,
                            "exposicao_pct": expo_etf, "tipo_origem": "ETF",
                        })
                    continue
            # Direct stock or non-explodable ETF
            exposures.append({
                "ativo": ticker, "setor": classificar_setor(ticker),
                "origem": "Direto", "peso_componente": peso_no_fundo,
                "peso_no_subfundo": 100,
                "exposicao_pct": peso_no_fundo, "tipo_origem": "Acao",
            })

        else:
            # RF, Caixa, Futuros, Opcoes — not explodable
            exposures.append({
                "ativo": comp, "setor": classe, "origem": "Direto",
                "peso_componente": peso_no_fundo, "peso_no_subfundo": 100,
                "exposicao_pct": peso_no_fundo, "tipo_origem": tipo,
            })

    if not exposures:
        return pd.DataFrame()

    df_exp = pd.DataFrame(exposures)
    return df_exp

# ==============================================================================
# PERIOD SELECTOR
# ==============================================================================
def period_selector(key_prefix: str):
    col_preset, col_dt1, col_dt2 = st.columns([2, 2, 2])
    today = date.today()
    presets = {
        "YTD 2026": (date(2026, 1, 2), today),
        "Jan/2026": (date(2026, 1, 2), date(2026, 1, 31)),
        "Fev/2026": (date(2026, 2, 3), today),
        "1M": (today - timedelta(days=30), today),
        "3M": (today - timedelta(days=90), today),
        "6M": (today - timedelta(days=180), today),
        "1A": (today - timedelta(days=365), today),
        "Personalizado": (date(2025, 1, 2), today),
    }
    # Track previous preset to detect changes and force-update date inputs
    prev_key = f"{key_prefix}_prev_preset"
    with col_preset:
        preset = st.selectbox("Periodo", list(presets.keys()), index=0, key=f"{key_prefix}_preset")
    default_start, default_end = presets[preset]
    # When preset changes, force-update session state for date inputs
    ini_key = f"{key_prefix}_dt_ini"
    fim_key = f"{key_prefix}_dt_fim"
    if st.session_state.get(prev_key) != preset:
        st.session_state[prev_key] = preset
        st.session_state[ini_key] = default_start
        st.session_state[fim_key] = default_end
    # Set default only if key not yet in session state (first load)
    if ini_key not in st.session_state:
        st.session_state[ini_key] = default_start
    if fim_key not in st.session_state:
        st.session_state[fim_key] = default_end
    with col_dt1:
        dt_inicio = st.date_input("Data inicio", format="DD/MM/YYYY", key=ini_key)
    with col_dt2:
        dt_fim = st.date_input("Data fim", format="DD/MM/YYYY", key=fim_key)
    return dt_inicio, dt_fim

# ==============================================================================
# PAGE 1: ATRIBUICAO IBOV
# ==============================================================================
def _legenda(texto: str):
    """Render a styled legend box below chart titles."""
    return f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">{texto}</div>"""

def render_tab_ibov():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
        <span style="color:{TAG_LARANJA};font-weight:600;">O que é esta página?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        Mostra a <b>atribuicao de performance do IBOV</b>: quanto cada setor e cada ação
        contribuiu para o retorno total do índice no período selecionado.<br>
        <b>Contribuição</b> = Peso da ação no índice x Retorno da ação, calculada <b>diariamente</b>
        e depois acumulada no período. A soma de todas = retorno do IBOV.
        </span></div>""", unsafe_allow_html=True)
    dt_inicio, dt_fim = period_selector("ibov")
    composition = fetch_ibov_composition()
    if not composition:
        st.error("Não foi possível obter a composição do IBOV via B3 API.")
        return
    tickers_sa = tuple(sorted(f"{tk}.SA" for tk in composition.keys()))
    # Buscar precos a partir de ~5 dias antes do inicio para garantir que temos
    # o Close do dia anterior (base do primeiro retorno). yfinance precisa de margem
    # para dias nao-uteis / feriados.
    start_fetch = (dt_inicio - timedelta(days=7)).strftime("%Y-%m-%d")
    end_str = (dt_fim + timedelta(days=1)).strftime("%Y-%m-%d")
    df_prices = fetch_prices(tickers_sa, start_fetch, end_str)
    if df_prices.empty:
        st.error("Não foi possível baixar preços históricos.")
        return
    # Filtrar para incluir apenas: ultimo dia ANTES de dt_inicio + todos os dias do periodo
    ibov_all = df_prices["^BVSP"].dropna()
    dates_before = ibov_all.index[ibov_all.index < pd.Timestamp(dt_inicio)]
    if len(dates_before) == 0:
        st.warning("Sem dados suficientes antes da data de inicio para calcular retornos.")
        return
    base_date = dates_before[-1]  # ultimo dia util ANTES do periodo
    mask = df_prices.index >= base_date
    df_prices_full = df_prices.loc[mask].copy()
    df_attr, df_daily = compute_ibov_daily_attribution(composition, df_prices_full)
    if df_attr.empty:
        st.warning("Sem dados suficientes para o período.")
        return
    df_sector = aggregate_by_sector(df_attr)
    # Retorno do IBOV = soma das contribuicoes (consistente com waterfall)
    sum_contrib = df_attr["contribution_pct"].sum()
    # Tambem calcular retorno direto do indice para referencia
    ibov_p = df_prices_full["^BVSP"].dropna()
    total_ret_index = (ibov_p.iloc[-1] / ibov_p.iloc[0] - 1) * 100 if len(ibov_p) >= 2 else 0
    total_ret = total_ret_index  # usar retorno direto do indice no card
    best_sec = df_sector.iloc[0] if not df_sector.empty else None
    worst_sec = df_sector.iloc[-1] if not df_sector.empty else None
    n_pos = (df_attr["contribution_pct"] > 0).sum()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cl = GREEN if total_ret >= 0 else RED
        st.markdown(metric_card("Retorno IBOV", f"<span style='color:{cl}'>{total_ret:+.2f}%</span>"), unsafe_allow_html=True)
    with c2:
        if best_sec is not None:
            st.markdown(metric_card("Melhor Setor", f"{best_sec['setor']}<br><span style='font-size:1rem;color:{GREEN}'>{best_sec['contribution_pct']:+.2f}%</span>"), unsafe_allow_html=True)
    with c3:
        if worst_sec is not None:
            st.markdown(metric_card("Pior Setor", f"{worst_sec['setor']}<br><span style='font-size:1rem;color:{RED}'>{worst_sec['contribution_pct']:+.2f}%</span>"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Ações no Indice", f"{len(df_attr)}<br><span style='font-size:1rem'>{n_pos} positivas</span>"), unsafe_allow_html=True)
    st.markdown("")
    # Waterfall
    st.markdown('<div class="tag-section-title">Contribuição por Setor (Waterfall)</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Cada barra mostra quanto um setor contribuiu para o retorno do IBOV. "
        "Barras <span style='color:#6BDE97'>verdes</span> = contribuição positiva. "
        "Barras <span style='color:#ED5A6E'>vermelhas</span> = contribuição negativa. "
        "A barra <span style='color:#FF8853'>laranja</span> no final = retorno total do IBOV (soma de tudo)."), unsafe_allow_html=True)
    df_s = df_sector.sort_values("contribution_pct", ascending=False)
    fig_wf = go.Figure(go.Waterfall(orientation="v",
        measure=["relative"] * len(df_s) + ["total"],
        x=list(df_s["setor"]) + ["IBOV Total"],
        y=list(df_s["contribution_pct"]) + [None],
        textposition="outside",
        text=[f"{v:+.2f}%" for v in df_s["contribution_pct"]] + [f"{total_ret:+.2f}%"],
        connector=dict(line=dict(color=TEXT_MUTED, width=1)),
        increasing=dict(marker=dict(color=GREEN)), decreasing=dict(marker=dict(color=RED)),
        totals=dict(marker=dict(color=TAG_LARANJA)), textfont=dict(size=9, color=TAG_OFFWHITE)))
    _chart_layout(fig_wf, "", height=480, y_suffix="%", margin_b=100)
    fig_wf.update_layout(xaxis_tickangle=-45, xaxis_tickfont=dict(size=10))
    st.plotly_chart(fig_wf, width='stretch', key="ibov_wf")
    # Waterfall by individual stock (Top 30)
    st.markdown('<div class="tag-section-title">Contribuição por Ativo (Waterfall Top 30)</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Mesmo conceito do waterfall setorial, mas decomposto por <b>ação individual</b>. "
        "Mostra as 30 acoes com maior contribuicao absoluta (positiva ou negativa). "
        "Barras <span style='color:#6BDE97'>verdes</span> = ação que ajudou, "
        "<span style='color:#ED5A6E'>vermelhas</span> = ação que prejudicou. "
        "A barra <span style='color:#FF8853'>laranja</span> = retorno total do IBOV."), unsafe_allow_html=True)
    df_top20 = df_attr.reindex(df_attr["contribution_pct"].abs().sort_values(ascending=False).index).head(30)
    df_top20 = df_top20.sort_values("contribution_pct", ascending=False)
    fig_wf_stock = go.Figure(go.Waterfall(orientation="v",
        measure=["relative"] * len(df_top20) + ["total"],
        x=list(df_top20["ticker"]) + ["IBOV Total"],
        y=list(df_top20["contribution_pct"]) + [None],
        textposition="outside",
        text=[f"{v:+.3f}%" for v in df_top20["contribution_pct"]] + [f"{total_ret:+.2f}%"],
        connector=dict(line=dict(color=TEXT_MUTED, width=1)),
        increasing=dict(marker=dict(color=GREEN)), decreasing=dict(marker=dict(color=RED)),
        totals=dict(marker=dict(color=TAG_LARANJA)), textfont=dict(size=8, color=TAG_OFFWHITE)))
    _chart_layout(fig_wf_stock, "", height=500, y_suffix="%", margin_b=100)
    fig_wf_stock.update_layout(xaxis_tickangle=-45, xaxis_tickfont=dict(size=9))
    st.plotly_chart(fig_wf_stock, width='stretch', key="ibov_wf_stock")

    # Bar + Table
    st.markdown('<div class="tag-section-title">Detalhamento Setorial</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> A barra horizontal mostra a contribuição de cada setor (mesma info do waterfall, "
        "em layout diferente). A tabela ao lado detalha: <b>Peso %</b> = quanto o setor pesa no IBOV, "
        "<b>Retorno %</b> = retorno medio do setor, <b>Contrib %</b> = Peso x Retorno."), unsafe_allow_html=True)
    col_c, col_t = st.columns([3, 2])
    with col_c:
        df_bar = df_s.sort_values("contribution_pct")
        colors = [GREEN if v >= 0 else RED for v in df_bar["contribution_pct"]]
        fig_bar = go.Figure(go.Bar(x=df_bar["contribution_pct"], y=df_bar["setor"], orientation="h",
            marker_color=colors, text=[f"{v:+.2f}%" for v in df_bar["contribution_pct"]],
            textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE)))
        _chart_layout(fig_bar, "", height=max(len(df_bar) * 28, 350), y_suffix="%")
        st.plotly_chart(fig_bar, width='stretch', key="ibov_bar")
    with col_t:
        df_show = df_s[["setor", "weight_pct", "sector_return_pct", "contribution_pct", "n_stocks"]].copy()
        df_show.columns = ["Setor", "Peso %", "Retorno %", "Contrib %", "N"]
        st.dataframe(df_show.style.format({"Peso %": "{:.2f}", "Retorno %": "{:+.2f}", "Contrib %": "{:+.3f}", "N": "{:.0f}"}), hide_index=True, height=min(len(df_show) * 38 + 45, 500))
    # Top/Bottom
    st.markdown('<div class="tag-section-title">Maiores Contribuições Individuais</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> As ações que mais contribuíram (<span style='color:#6BDE97'>verde</span>, "
        "esquerda) e mais prejudicaram (<span style='color:#ED5A6E'>vermelho</span>, direita) o retorno do IBOV. "
        "Uma ação com peso grande e retorno alto contribui muito; uma com peso grande e retorno negativo prejudica."), unsafe_allow_html=True)
    n_show = min(10, len(df_attr))
    df_top = df_attr.nlargest(n_show, "contribution_pct")
    df_bot = df_attr.nsmallest(n_show, "contribution_pct")
    col_tp, col_bt = st.columns(2)
    with col_tp:
        fig_top = go.Figure(go.Bar(x=df_top["contribution_pct"].values[::-1], y=df_top["ticker"].values[::-1], orientation="h", marker_color=GREEN, text=[f"{v:+.3f}%" for v in df_top["contribution_pct"].values[::-1]], textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE)))
        _chart_layout(fig_top, f"Top {n_show} Contribuidores", height=380)
        st.plotly_chart(fig_top, width='stretch', key="ibov_top")
    with col_bt:
        fig_bot = go.Figure(go.Bar(x=df_bot["contribution_pct"].values, y=df_bot["ticker"].values, orientation="h", marker_color=RED, text=[f"{v:+.3f}%" for v in df_bot["contribution_pct"].values], textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE)))
        _chart_layout(fig_bot, f"Bottom {n_show} Detratores", height=380)
        st.plotly_chart(fig_bot, width='stretch', key="ibov_bot")
    # Treemap
    with st.expander(f"Tabela Completa — {len(df_attr)} acoes", expanded=False):
        df_full = df_attr[["ticker", "setor", "weight_pct", "return_pct", "contribution_pct"]].copy()
        df_full.columns = ["Acao", "Setor", "Peso %", "Retorno %", "Contrib %"]
        st.dataframe(df_full.style.format({"Peso %": "{:.2f}", "Retorno %": "{:+.2f}", "Contrib %": "{:+.3f}"}), hide_index=True, height=600)

# ==============================================================================
# PAGE 2: SYNTA ATTRIBUTION
# ==============================================================================
def render_tab_synta():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
        <span style="color:{TAG_LARANJA};font-weight:600;">O que é esta página?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        Mostra quanto cada ativo/fundo da carteira contribuiu para o retorno total do Synta.<br>
        <b>Metodo:</b> Contribuição = Peso do ativo no dia anterior x Retorno do ativo no dia (via PU).
        Para futuros, usa o ajuste diário (P&amp;L real). Contribuições são escaladas para somar o retorno da cota.
        </span></div>""", unsafe_allow_html=True)
    fundo_sel = st.radio("Fundo", list(FUNDOS_CONFIG.keys()), horizontal=True, key="synta_fundo")
    dt_inicio, dt_fim = period_selector("synta")
    start_str, end_str = dt_inicio.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")
    df_ts = load_synta_timeseries(fundo_sel, start_str, end_str)
    if df_ts.empty:
        st.warning(f"Sem dados de XML para {fundo_sel} no período.")
        return
    df_attr = compute_synta_attribution(df_ts, period_start=start_str)
    if df_attr.empty:
        st.warning("Dados insuficientes (minimo 2 dias).")
        return
    ret_total = df_attr["retorno_total_fundo"].iloc[0]
    sum_contrib = df_attr["contribution_pct"].sum()
    dates = sorted(df_ts["data"].unique())
    pl_last = df_ts[df_ts["data"] == dates[-1]]["patliq"].iloc[0]
    best, worst = df_attr.iloc[0], df_attr.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cl = GREEN if ret_total >= 0 else RED
        st.markdown(metric_card("Retorno Fundo", f"<span style='color:{cl}'>{ret_total:+.2f}%</span>"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("PL Atual", f"R$ {pl_last/1e6:.1f}M"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Maior Contrib.", f"{best['componente']}<br><span style='font-size:0.9rem;color:{GREEN}'>{best['contribution_pct']:+.2f}%</span>"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Menor Contrib.", f"{worst['componente']}<br><span style='font-size:0.9rem;color:{RED}'>{worst['contribution_pct']:+.2f}%</span>"), unsafe_allow_html=True)
    st.markdown("")
    # Waterfall
    st.markdown('<div class="tag-section-title">Waterfall — Contribuição por Componente</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Cada barra mostra quanto aquele componente da carteira contribuiu para o retorno total "
        "do fundo no período. Barras <span style='color:#6BDE97'>verdes</span> = contribuição positiva, "
        "<span style='color:#ED5A6E'>vermelhas</span> = negativa. A barra <span style='color:#FF8853'>laranja</span> = retorno total "
        "(soma). A contribuição e calculada <b>diariamente</b> (peso dia anterior x retorno do dia) e depois acumulada no período."), unsafe_allow_html=True)
    df_wf = df_attr.sort_values("contribution_pct", ascending=False)
    fig_wf = go.Figure(go.Waterfall(orientation="v",
        measure=["relative"] * len(df_wf) + ["total"],
        x=list(df_wf["componente"]) + ["Total"], y=list(df_wf["contribution_pct"]) + [None],
        textposition="outside", text=[f"{v:+.2f}%" for v in df_wf["contribution_pct"]] + [f"{sum_contrib:+.2f}%"],
        connector=dict(line=dict(color=TEXT_MUTED, width=1)),
        increasing=dict(marker=dict(color=GREEN)), decreasing=dict(marker=dict(color=RED)),
        totals=dict(marker=dict(color=TAG_LARANJA)), textfont=dict(size=8, color=TAG_OFFWHITE)))
    _chart_layout(fig_wf, "", height=500, y_suffix="%", margin_b=140)
    fig_wf.update_layout(xaxis_tickangle=-45, xaxis_tickfont=dict(size=9))
    st.plotly_chart(fig_wf, width='stretch', key="synta_wf")

    # ── Waterfall — Contribuicao por Ativo Individual (exploded) ──
    st.markdown('<div class="tag-section-title">Waterfall — Contribuição Estimada por Ativo Individual</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Como ler:</b> Distribui a contribuição de cada sub-fundo entre as ações que ele detem (via dados CVM). "
        "A contribuição de cada ação e <b>estimada</b> proporcionalmente ao peso dela no sub-fundo.<br>"
        "<span style='color:#FF8853;'>⚠ Importante:</span> As carteiras dos sub-fundos vem do CVM e podem ter "
        "<b>defasagem de até 3-6 meses</b>. Os pesos reais podem ter mudado. Use como <b>indicacao direcional</b>, "
        "não como valor exato. Top 30 ativos por contribuição absoluta."), unsafe_allow_html=True)

    # Explode sub-fund contributions to individual stocks
    df_exp = explode_fund_to_stocks(fundo_sel, end_str)
    if not df_exp.empty:
        # For each sub-fund in df_attr, distribute its contribution among its stocks
        stock_contribs = {}  # ticker -> cumulative contribution
        stock_setores = {}   # ticker -> sector

        for _, attr_row in df_attr.iterrows():
            comp_name = attr_row["componente"]
            comp_tipo = attr_row["tipo"]
            comp_contrib = attr_row["contribution_pct"]

            if comp_tipo == "Fundo":
                # Find stocks from this sub-fund in exploded data
                # Match by origin name
                df_sub_stocks = df_exp[df_exp["origem"] == comp_name]
                if df_sub_stocks.empty:
                    # Try matching with partial name
                    df_sub_stocks = df_exp[df_exp["origem"].str.contains(comp_name[:10], na=False)]

                if not df_sub_stocks.empty and df_sub_stocks["exposicao_pct"].sum() > 0:
                    # Distribute contribution proportionally by exposure weight
                    total_expo = df_sub_stocks["exposicao_pct"].sum()
                    for _, stk_row in df_sub_stocks.iterrows():
                        tk = stk_row["ativo"]
                        if not _is_stock_ticker(tk) or _is_option_ticker(tk):
                            continue
                        prop = stk_row["exposicao_pct"] / total_expo
                        stk_contrib = comp_contrib * prop
                        stock_contribs[tk] = stock_contribs.get(tk, 0) + stk_contrib
                        stock_setores[tk] = stk_row.get("setor", classificar_setor(tk))
                else:
                    # Can't explode — keep as fund
                    stock_contribs[comp_name] = stock_contribs.get(comp_name, 0) + comp_contrib
                    stock_setores[comp_name] = _classificar_componente(comp_name, comp_tipo)
            elif comp_tipo == "Acao/ETF":
                tk = comp_name
                if tk in ETF_INDEX_MAP:
                    # ETF — distribute among ETF components
                    df_etf_stocks = df_exp[(df_exp["origem"].str.contains(tk, na=False)) & (df_exp["tipo_origem"].isin(["ETF", "Fundo>ETF"]))]
                    if not df_etf_stocks.empty and df_etf_stocks["exposicao_pct"].sum() > 0:
                        total_expo = df_etf_stocks["exposicao_pct"].sum()
                        for _, stk_row in df_etf_stocks.iterrows():
                            etk = stk_row["ativo"]
                            if not _is_stock_ticker(etk) or _is_option_ticker(etk):
                                continue
                            prop = stk_row["exposicao_pct"] / total_expo
                            stk_contrib = comp_contrib * prop
                            stock_contribs[etk] = stock_contribs.get(etk, 0) + stk_contrib
                            stock_setores[etk] = stk_row.get("setor", classificar_setor(etk))
                    else:
                        stock_contribs[tk] = stock_contribs.get(tk, 0) + comp_contrib
                        stock_setores[tk] = classificar_setor(tk)
                else:
                    # Direct stock
                    stock_contribs[tk] = stock_contribs.get(tk, 0) + comp_contrib
                    stock_setores[tk] = classificar_setor(tk)
            else:
                # RF, Caixa, Futuros, etc — keep as aggregate
                stock_contribs[comp_name] = stock_contribs.get(comp_name, 0) + comp_contrib
                stock_setores[comp_name] = _classificar_componente(comp_name, comp_tipo)

        if stock_contribs:
            df_stk_attr = pd.DataFrame([
                {"ativo": tk, "setor": stock_setores.get(tk, ""), "contrib_pct": c}
                for tk, c in stock_contribs.items()
            ]).sort_values("contrib_pct", ascending=False)

            # Top 30 by absolute contribution
            df_stk_top = df_stk_attr.reindex(df_stk_attr["contrib_pct"].abs().sort_values(ascending=False).index).head(30)
            df_stk_top = df_stk_top.sort_values("contrib_pct", ascending=False)
            # Aggregate remaining into "Outros"
            others_contrib = df_stk_attr.loc[~df_stk_attr.index.isin(df_stk_top.index), "contrib_pct"].sum()

            stk_labels = list(df_stk_top["ativo"])
            stk_values = list(df_stk_top["contrib_pct"])
            if abs(others_contrib) > 0.001:
                stk_labels.append("Outros")
                stk_values.append(others_contrib)

            fig_stk_wf = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative"] * len(stk_values) + ["total"],
                x=stk_labels + ["Total"],
                y=stk_values + [None],
                textposition="outside",
                text=[f"{v:+.3f}%" for v in stk_values] + [f"{sum_contrib:+.2f}%"],
                connector=dict(line=dict(color=TEXT_MUTED, width=0.8)),
                increasing=dict(marker=dict(color=GREEN)),
                decreasing=dict(marker=dict(color=RED)),
                totals=dict(marker=dict(color=TAG_LARANJA)),
                textfont=dict(size=7, color=TAG_OFFWHITE),
            ))
            _chart_layout(fig_stk_wf, "", height=550, y_suffix="%", margin_b=160)
            fig_stk_wf.update_layout(xaxis_tickangle=-55, xaxis_tickfont=dict(size=8))
            st.plotly_chart(fig_stk_wf, width='stretch', key="synta_stk_wf")

            # Detail table
            df_stk_show = df_stk_attr[["ativo", "setor", "contrib_pct"]].copy()
            df_stk_show.columns = ["Ativo", "Setor", "Contrib Est. (%)"]
            st.dataframe(df_stk_show.style.format({"Contrib Est. (%)": "{:+.4f}"}),
                          hide_index=True, height=min(len(df_stk_show) * 35 + 45, 500))
    else:
        st.info("Sem dados de carteiras explodidas para calcular contribuição por ativo.")

    # Table
    st.markdown('<div class="tag-section-title">Detalhamento por Componente</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Colunas:</b> <b>Peso Ini/Fim %</b> = peso do componente no PL no inicio e fim do período. "
        "<b>Contrib %</b> = contribuição acumulada no período (soma diaria de peso(t-1) x retorno(t))."), unsafe_allow_html=True)
    df_show = df_attr[["componente", "tipo", "peso_inicio", "peso_fim", "contribution_pct"]].copy()
    df_show.columns = ["Componente", "Tipo", "Peso Ini %", "Peso Fim %", "Contrib %"]
    st.dataframe(df_show.style.format({"Peso Ini %": "{:.2f}", "Peso Fim %": "{:.2f}", "Contrib %": "{:+.3f}"}), hide_index=True, height=min(len(df_show) * 38 + 45, 600))
    # (Stacked area "Evolucao dos Pesos" removed — same chart available on Carteira Explodida page)

# ==============================================================================
# PAGE 3: BRINSON-FACHLER
# ==============================================================================
def render_tab_brinson():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30; border-radius:10px; padding:16px 20px; margin-bottom:18px;">
        <span style="color:{TAG_LARANJA};font-weight:600;font-size:1rem;">O que é o Brinson-Fachler?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        É um método clássico que responde: <b>"Por que o fundo rendeu diferente do IBOV?"</b><br>
        Ele decompõe a diferença de retorno (<b>excesso</b>) em 3 efeitos:<br>
        <b style="color:{TAG_CHART_COLORS[0]};">Alocação</b> = o fundo alocou nos setores certos?&emsp;
        <b style="color:{TAG_CHART_COLORS[1]};">Seleção</b> = escolheu os melhores ativos dentro de cada setor?&emsp;
        <b style="color:{TAG_CHART_COLORS[2]};">Interação</b> = efeito combinado dos dois.<br>
        <span style="color:{TAG_LARANJA};">⚠ Os pesos setoriais do fundo são calculados via <b>carteira explodida</b> (sub-fundos decompostos em
        ações individuais via dados CVM). As carteiras podem ter defasagem de até 3-6 meses.</span>
        </span></div>""", unsafe_allow_html=True)
    fundo_sel = st.radio("Fundo", list(FUNDOS_CONFIG.keys()), horizontal=True, key="bf_fundo")
    dt_inicio, dt_fim = period_selector("bf")
    start_str, end_str = dt_inicio.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")
    df_ts = load_synta_timeseries(fundo_sel, start_str, end_str)
    if df_ts.empty:
        st.warning(f"Sem dados para {fundo_sel}.")
        return
    df_fund_attr = compute_synta_attribution(df_ts, period_start=start_str)
    if df_fund_attr.empty:
        st.warning("Dados insuficientes.")
        return
    ret_fundo = df_fund_attr["retorno_total_fundo"].iloc[0]
    composition = fetch_ibov_composition()
    if not composition:
        st.error("Composição IBOV indisponível.")
        return
    tickers_sa = tuple(sorted(f"{tk}.SA" for tk in composition.keys()))
    start_fetch = (dt_inicio - timedelta(days=7)).strftime("%Y-%m-%d")
    end_yf = (dt_fim + timedelta(days=1)).strftime("%Y-%m-%d")
    df_prices = fetch_prices(tickers_sa, start_fetch, end_yf)
    if df_prices.empty:
        st.error("Sem precos.")
        return
    ibov_all = df_prices["^BVSP"].dropna()
    dates_before = ibov_all.index[ibov_all.index < pd.Timestamp(dt_inicio)]
    if len(dates_before) == 0:
        st.warning("Sem dados antes do inicio.")
        return
    base_date = dates_before[-1]
    df_prices_bf = df_prices.loc[df_prices.index >= base_date].copy()
    df_ibov_attr, _ = compute_ibov_daily_attribution(composition, df_prices_bf)
    if df_ibov_attr.empty:
        st.warning("Sem dados IBOV.")
        return
    df_ibov_sector = aggregate_by_sector(df_ibov_attr)
    ibov_p = df_prices_bf["^BVSP"].dropna()
    ret_ibov = (ibov_p.iloc[-1] / ibov_p.iloc[0] - 1) * 100 if len(ibov_p) >= 2 else 0
    # ── Build fund weights/returns using EXPLODED portfolio (sector-level) ──
    # Explode the fund to get actual stock-level sector exposures
    df_exp = explode_fund_to_stocks(fundo_sel, end_str)

    # Separate equity from non-equity exposures
    equity_tipos = ["Fundo", "ETF", "Acao", "Fundo>ETF"]
    non_equity_tipos = ["RF", "Caixa", "Futuro", "Opcao", "Opcao Futuro"]

    fund_w, fund_r = {}, {}

    if not df_exp.empty:
        df_eq_exp = df_exp[df_exp["tipo_origem"].isin(equity_tipos)]
        df_neq_exp = df_exp[~df_exp["tipo_origem"].isin(equity_tipos)]

        # Equity: group by REAL sector from exploded portfolio
        if not df_eq_exp.empty:
            sec_weights = df_eq_exp.groupby("setor")["exposicao_pct"].sum().to_dict()
            for setor, w in sec_weights.items():
                fund_w[setor] = w

        # Non-equity: group by broad category (Renda Fixa, Caixa, Futuros, etc.)
        if not df_neq_exp.empty:
            for _, row_ne in df_neq_exp.iterrows():
                cat = row_ne["setor"]  # already classified by _classificar_componente
                fund_w[cat] = fund_w.get(cat, 0) + row_ne["exposicao_pct"]

        # Build stock-level contribution mapping (same logic as stock waterfall)
        stock_contribs_bf = {}
        stock_setores_bf = {}
        for _, attr_row in df_fund_attr.iterrows():
            comp_name = attr_row["componente"]
            comp_tipo = attr_row["tipo"]
            comp_contrib = attr_row["contribution_pct"]

            if comp_tipo == "Fundo":
                df_sub_stocks = df_exp[df_exp["origem"] == comp_name]
                if df_sub_stocks.empty:
                    df_sub_stocks = df_exp[df_exp["origem"].str.contains(comp_name[:10], na=False)]
                if not df_sub_stocks.empty and df_sub_stocks["exposicao_pct"].sum() > 0:
                    total_expo = df_sub_stocks["exposicao_pct"].sum()
                    for _, stk_row in df_sub_stocks.iterrows():
                        tk = stk_row["ativo"]
                        prop = stk_row["exposicao_pct"] / total_expo
                        stk_contrib = comp_contrib * prop
                        stock_contribs_bf[tk] = stock_contribs_bf.get(tk, 0) + stk_contrib
                        stock_setores_bf[tk] = stk_row.get("setor", classificar_setor(tk))
                else:
                    stock_contribs_bf[comp_name] = stock_contribs_bf.get(comp_name, 0) + comp_contrib
                    stock_setores_bf[comp_name] = _classificar_componente(comp_name, comp_tipo)
            elif comp_tipo == "Acao/ETF":
                tk = comp_name
                if tk in ETF_INDEX_MAP:
                    df_etf_stocks = df_exp[(df_exp["origem"].str.contains(tk, na=False)) & (df_exp["tipo_origem"].isin(["ETF", "Fundo>ETF"]))]
                    if not df_etf_stocks.empty and df_etf_stocks["exposicao_pct"].sum() > 0:
                        total_expo = df_etf_stocks["exposicao_pct"].sum()
                        for _, stk_row in df_etf_stocks.iterrows():
                            etk = stk_row["ativo"]
                            prop = stk_row["exposicao_pct"] / total_expo
                            stk_contrib = comp_contrib * prop
                            stock_contribs_bf[etk] = stock_contribs_bf.get(etk, 0) + stk_contrib
                            stock_setores_bf[etk] = stk_row.get("setor", classificar_setor(etk))
                    else:
                        stock_contribs_bf[tk] = stock_contribs_bf.get(tk, 0) + comp_contrib
                        stock_setores_bf[tk] = classificar_setor(tk)
                else:
                    stock_contribs_bf[tk] = stock_contribs_bf.get(tk, 0) + comp_contrib
                    stock_setores_bf[tk] = classificar_setor(tk)
            else:
                stock_contribs_bf[comp_name] = stock_contribs_bf.get(comp_name, 0) + comp_contrib
                stock_setores_bf[comp_name] = _classificar_componente(comp_name, comp_tipo)

        # Aggregate contributions by sector to get sector-level returns
        sector_contrib = {}
        for tk, contrib in stock_contribs_bf.items():
            setor = stock_setores_bf.get(tk, "Outros")
            sector_contrib[setor] = sector_contrib.get(setor, 0) + contrib

        # Fund return per sector = sector_contribution / sector_weight * 100
        for s in fund_w:
            w = fund_w[s]
            c = sector_contrib.get(s, 0)
            fund_r[s] = c / w * 100 if w > 0 else 0
    else:
        # Fallback: use old method if explosion not available
        for _, row in df_fund_attr.iterrows():
            setor = _classificar_componente(row["componente"], row["tipo"])
            peso_avg = (row["peso_inicio"] + row["peso_fim"]) / 2
            fund_w[setor] = fund_w.get(setor, 0) + peso_avg
            fund_r[setor] = fund_r.get(setor, 0) + row["contribution_pct"]
        for s in fund_w:
            w = fund_w[s]
            fund_r[s] = fund_r[s] / w * 100 if w > 0 else 0
    bench_w = dict(zip(df_ibov_sector["setor"], df_ibov_sector["weight_pct"]))
    bench_r = dict(zip(df_ibov_sector["setor"], df_ibov_sector["sector_return_pct"]))
    df_bf = compute_brinson_fachler(fund_w, fund_r, bench_w, bench_r, ret_ibov)
    excess = ret_fundo - ret_ibov
    ta, ts, ti = df_bf["alocacao"].sum(), df_bf["selecao"].sum(), df_bf["interacao"].sum()

    # --- METRICS ---
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        cl = GREEN if ret_fundo >= 0 else RED
        st.markdown(metric_card("Ret. Fundo", f"<span style='color:{cl}'>{ret_fundo:+.2f}%</span>"), unsafe_allow_html=True)
    with c2:
        cl = GREEN if ret_ibov >= 0 else RED
        st.markdown(metric_card("Ret. IBOV", f"<span style='color:{cl}'>{ret_ibov:+.2f}%</span>"), unsafe_allow_html=True)
    with c3:
        cl = GREEN if excess >= 0 else RED
        st.markdown(metric_card("Excesso", f"<span style='color:{cl}'>{excess:+.2f}%</span>"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Ef. Alocação", f"{ta:+.2f}%"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("Ef. Seleção", f"{ts:+.2f}%"), unsafe_allow_html=True)
    st.markdown("")

    # =============================================
    # GRAFICO 1: Waterfall — Decomposicao do Excesso
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Decomposição do Excesso de Retorno</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Como ler:</b> Cada barra mostra quanto cada efeito contribuiu para a diferença entre o fundo e o IBOV.
        A soma dos 3 efeitos = excesso total.<br>
        <b style="color:{TAG_CHART_COLORS[0]};">Alocação</b>: (Peso Fundo - Peso IBOV) x (Ret. Setor IBOV - Ret. Total IBOV) &mdash;
        <i>o fundo apostou nos setores certos?</i><br>
        <b style="color:{TAG_CHART_COLORS[1]};">Seleção</b>: Peso IBOV x (Ret. Setor Fundo - Ret. Setor IBOV) &mdash;
        <i>dentro de cada setor, o fundo escolheu os melhores ativos?</i><br>
        <b style="color:{TAG_CHART_COLORS[2]};">Interação</b>: (Peso Fundo - Peso IBOV) x (Ret. Setor Fundo - Ret. Setor IBOV) &mdash;
        <i>efeito cruzado entre alocacao e selecao.</i>
        </div>""", unsafe_allow_html=True)
    fig_dec = go.Figure(go.Waterfall(orientation="v", measure=["relative"] * 3 + ["total"],
        x=["Alocacao", "Selecao", "Interacao", "Excesso Total"],
        y=[ta, ts, ti, None], text=[f"{ta:+.2f}%", f"{ts:+.2f}%", f"{ti:+.2f}%", f"{excess:+.2f}%"],
        textposition="outside", connector=dict(line=dict(color=TEXT_MUTED)),
        increasing=dict(marker=dict(color=GREEN)), decreasing=dict(marker=dict(color=RED)),
        totals=dict(marker=dict(color=TAG_LARANJA)), textfont=dict(size=13, color=TAG_OFFWHITE)))
    _chart_layout(fig_dec, "", height=400, y_suffix="%")
    st.plotly_chart(fig_dec, width='stretch', key="bf_wf")

    # =============================================
    # GRAFICO 2: Comparativo de Pesos — Fundo vs IBOV
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Comparativo de Alocação por Setor — Fundo vs IBOV</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Como ler:</b> Compara quanto (%) o fundo e o IBOV tem em cada setor.
        Barras alinhadas = alocacao similar. Diferenca grande = aposta ativa do gestor.
        Os pesos do fundo são calculados a partir da <b>carteira explodida</b> (sub-fundos decompostos em ações individuais via CVM).
        Categorias como "Renda Fixa" e "Caixa" aparecem no fundo mas nao no IBOV.
        <br><span style="color:{TAG_LARANJA};">⚠</span> Pesos do fundo baseados em dados CVM (defasagem até 3-6 meses).
        </div>""", unsafe_allow_html=True)
    df_bfs = df_bf.sort_values("peso_bench", ascending=True)
    fig_pesos = go.Figure()
    fig_pesos.add_trace(go.Bar(y=df_bfs["setor"], x=df_bfs["peso_fundo"], name=f"{fundo_sel}",
        orientation="h", marker_color=TAG_LARANJA, text=df_bfs["peso_fundo"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside", textfont=dict(size=10, color=TAG_OFFWHITE)))
    fig_pesos.add_trace(go.Bar(y=df_bfs["setor"], x=df_bfs["peso_bench"], name="IBOV",
        orientation="h", marker_color=TAG_CHART_COLORS[1], text=df_bfs["peso_bench"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside", textfont=dict(size=10, color=TAG_OFFWHITE)))
    _chart_layout(fig_pesos, "", height=max(len(df_bfs) * 40, 380), y_suffix="")
    fig_pesos.update_layout(barmode="group", xaxis_title="Peso (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_pesos, width='stretch', key="bf_pesos")

    # =============================================
    # GRAFICO 3: Comparativo de Retornos por Setor
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Comparativo de Retorno por Setor — Fundo vs IBOV</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Como ler:</b> Compara o retorno (%) dos ativos do fundo vs IBOV em cada setor.
        Se a barra laranja ({fundo_sel}) e maior que a azul (IBOV), o fundo selecionou
        ativos melhores naquele setor. Os retornos do fundo sao estimados via atribuicao por componente,
        distribuida proporcionalmente entre as acoes de cada sub-fundo (carteira CVM).
        <br><span style="color:{TAG_LARANJA};">⚠</span> Retornos setoriais do fundo são <b>estimativas</b> (carteiras CVM com defasagem).
        </div>""", unsafe_allow_html=True)
    df_bfr = df_bf.sort_values("ret_bench", ascending=True)
    fig_rets = go.Figure()
    fig_rets.add_trace(go.Bar(y=df_bfr["setor"], x=df_bfr["ret_fundo"], name=f"{fundo_sel}",
        orientation="h", marker_color=TAG_LARANJA, text=df_bfr["ret_fundo"].apply(lambda x: f"{x:+.1f}%"),
        textposition="outside", textfont=dict(size=10, color=TAG_OFFWHITE)))
    fig_rets.add_trace(go.Bar(y=df_bfr["setor"], x=df_bfr["ret_bench"], name="IBOV",
        orientation="h", marker_color=TAG_CHART_COLORS[1], text=df_bfr["ret_bench"].apply(lambda x: f"{x:+.1f}%"),
        textposition="outside", textfont=dict(size=10, color=TAG_OFFWHITE)))
    _chart_layout(fig_rets, "", height=max(len(df_bfr) * 40, 380), y_suffix="")
    fig_rets.update_layout(barmode="group", xaxis_title="Retorno (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_rets, width='stretch', key="bf_rets")

    # =============================================
    # GRAFICO 4: Efeitos por Setor (Stacked Bar)
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Efeitos Brinson-Fachler por Setor</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Como ler:</b> Cada setor e decomposto nos 3 efeitos. Barras para a <b>direita</b> = contribuíram
        positivamente para o excesso. Barras para a <b>esquerda</b> = prejudicaram.
        A soma de todos os setores = excesso total do fundo vs IBOV.
        </div>""", unsafe_allow_html=True)
    df_bfs2 = df_bf.sort_values("total", ascending=True)
    fig_s = go.Figure()
    fig_s.add_trace(go.Bar(y=df_bfs2["setor"], x=df_bfs2["alocacao"], name="Alocacao", orientation="h",
        marker_color=TAG_CHART_COLORS[0], hovertemplate="%{y}: %{x:+.3f}%"))
    fig_s.add_trace(go.Bar(y=df_bfs2["setor"], x=df_bfs2["selecao"], name="Selecao", orientation="h",
        marker_color=TAG_CHART_COLORS[1], hovertemplate="%{y}: %{x:+.3f}%"))
    fig_s.add_trace(go.Bar(y=df_bfs2["setor"], x=df_bfs2["interacao"], name="Interacao", orientation="h",
        marker_color=TAG_CHART_COLORS[2], hovertemplate="%{y}: %{x:+.3f}%"))
    _chart_layout(fig_s, "", height=max(len(df_bfs2) * 35, 380), y_suffix="%")
    fig_s.update_layout(barmode="relative", xaxis_title="Efeito (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_s, width='stretch', key="bf_stack")

    # =============================================
    # GRAFICO 5: Top Setores — Quem mais ajudou/prejudicou
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Top Setores — Maiores Contribuições para o Excesso</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Como ler:</b> Ranking dos setores que mais ajudaram (<span style="color:{GREEN};">verde</span>)
        ou prejudicaram (<span style="color:{RED};">vermelho</span>) o excesso de retorno do fundo
        em relacao ao IBOV. O efeito total de cada setor = Alocacao + Selecao + Interacao.
        </div>""", unsafe_allow_html=True)
    df_top = df_bf[["setor", "total"]].sort_values("total", ascending=True).copy()
    colors_top = [GREEN if v >= 0 else RED for v in df_top["total"]]
    fig_top = go.Figure(go.Bar(
        y=df_top["setor"], x=df_top["total"], orientation="h",
        marker_color=colors_top,
        text=df_top["total"].apply(lambda x: f"{x:+.3f}%"),
        textposition="outside", textfont=dict(size=11, color=TAG_OFFWHITE),
        hovertemplate="%{y}: %{x:+.3f}%<extra></extra>"
    ))
    _chart_layout(fig_top, "", height=max(len(df_top) * 35, 380))
    fig_top.update_layout(xaxis_title="Efeito Total (%)")
    st.plotly_chart(fig_top, width='stretch', key="bf_top")

    # =============================================
    # TABELA com legenda
    # =============================================
    st.markdown(f"""<span style="color:{TAG_LARANJA};font-weight:600;font-size:1.05rem;">
        Tabela Detalhada por Setor</span>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_VERMELHO}20;border-radius:8px;
        padding:10px 14px;margin-bottom:10px;font-size:0.82rem;color:{TEXT_MUTED};">
        <b>Colunas:</b><br>
        <b>Peso Fundo/IBOV %</b> = quanto (%) cada setor representa na carteira do fundo e no IBOV.<br>
        <b>Ret Fundo/IBOV %</b> = retorno dos ativos daquele setor no fundo e no IBOV no período.<br>
        <b>Alocação/Seleção/Interação %</b> = os 3 efeitos Brinson-Fachler para cada setor.<br>
        <b>Total %</b> = soma dos 3 efeitos; quanto aquele setor contribuiu para o excesso de retorno.
        </div>""", unsafe_allow_html=True)
    df_bf_show = df_bf[["setor", "peso_fundo", "peso_bench", "ret_fundo", "ret_bench", "alocacao", "selecao", "interacao", "total"]].copy()
    df_bf_show.columns = ["Setor", "Peso Fundo %", "Peso IBOV %", "Ret Fundo %", "Ret IBOV %", "Alocacao %", "Selecao %", "Interacao %", "Total %"]
    st.dataframe(df_bf_show.style.format({"Peso Fundo %": "{:.1f}", "Peso IBOV %": "{:.1f}", "Ret Fundo %": "{:+.2f}", "Ret IBOV %": "{:+.2f}", "Alocacao %": "{:+.3f}", "Selecao %": "{:+.3f}", "Interacao %": "{:+.3f}", "Total %": "{:+.3f}"}), hide_index=True)

    # =============================================
    # RESUMO FINAL
    # =============================================
    # Construir interpretacao automatica
    best_s = df_bf.loc[df_bf["total"].idxmax()]
    worst_s = df_bf.loc[df_bf["total"].idxmin()]
    efeito_desc = {"alocacao": "alocacao setorial", "selecao": "selecao de ativos", "interacao": "interacao"}
    maior_ef_name = max(["alocacao", "selecao", "interacao"], key=lambda e: abs(df_bf[e].sum()))
    maior_ef_val = df_bf[maior_ef_name].sum()
    dir_ef = "positivamente" if maior_ef_val > 0 else "negativamente"
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_LARANJA}40; border-radius:10px; padding:16px 20px; margin-top:10px;">
        <span style="color:{TAG_LARANJA};font-weight:600;font-size:1rem;">Resumo da Analise</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        O <b>{fundo_sel}</b> rendeu <b>{ret_fundo:+.2f}%</b> no período, enquanto o IBOV rendeu <b>{ret_ibov:+.2f}%</b>,
        gerando um excesso de <b>{excess:+.2f}%</b>.<br><br>
        O efeito mais relevante foi a <b>{efeito_desc[maior_ef_name]}</b>,
        que impactou {dir_ef} em <b>{maior_ef_val:+.2f}%</b>.<br>
        O setor que mais contribuiu positivamente foi <b>{best_s["setor"]}</b> ({best_s["total"]:+.3f}%),
        e o que mais prejudicou foi <b>{worst_s["setor"]}</b> ({worst_s["total"]:+.3f}%).
        </span></div>""", unsafe_allow_html=True)

# ==============================================================================
# PAGE 4: COMPARATIVO
# ==============================================================================
def render_tab_comparativo():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
        <span style="color:{TAG_LARANJA};font-weight:600;">O que é esta página?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        Compara o desempenho dos fundos Synta FIA e FIA II contra o IBOV.
        <b>Excesso</b> = retorno do fundo - retorno do IBOV. Positivo = fundo superou o índice.
        </span></div>""", unsafe_allow_html=True)
    dt_inicio, dt_fim = period_selector("comp")
    start_str, end_str = dt_inicio.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d")
    df_ts_fia = load_synta_timeseries("Synta FIA", start_str, end_str)
    df_ts_fia2 = load_synta_timeseries("Synta FIA II", start_str, end_str)
    has_fia, has_fia2 = not df_ts_fia.empty, not df_ts_fia2.empty
    if not has_fia and not has_fia2:
        st.warning("Sem dados para nenhum fundo.")
        return
    composition = fetch_ibov_composition()
    if not composition:
        st.error("Composição IBOV indisponível.")
        return
    tickers_sa = tuple(sorted(f"{tk}.SA" for tk in composition.keys()))
    start_fetch = (dt_inicio - timedelta(days=7)).strftime("%Y-%m-%d")
    end_yf = (dt_fim + timedelta(days=1)).strftime("%Y-%m-%d")
    df_prices = fetch_prices(tickers_sa, start_fetch, end_yf)
    if df_prices.empty:
        st.error("Sem precos.")
        return
    # Pegar base date (ultimo dia util ANTES do periodo) para calculo correto do retorno
    ibov_all = df_prices["^BVSP"].dropna()
    dates_before = ibov_all.index[ibov_all.index < pd.Timestamp(dt_inicio)]
    if len(dates_before) == 0:
        st.warning("Sem dados suficientes antes da data de inicio.")
        return
    base_date = dates_before[-1]
    ibov_p = ibov_all.loc[ibov_all.index >= base_date]
    ret_ibov = (ibov_p.iloc[-1] / ibov_p.iloc[0] - 1) * 100 if len(ibov_p) >= 2 else 0
    ret_fia, ret_fia2, df_a_fia, df_a_fia2 = 0, 0, pd.DataFrame(), pd.DataFrame()
    if has_fia:
        df_a_fia = compute_synta_attribution(df_ts_fia, period_start=start_str)
        if not df_a_fia.empty:
            ret_fia = df_a_fia["retorno_total_fundo"].iloc[0]
    if has_fia2:
        df_a_fia2 = compute_synta_attribution(df_ts_fia2, period_start=start_str)
        if not df_a_fia2.empty:
            ret_fia2 = df_a_fia2["retorno_total_fundo"].iloc[0]
    ex_fia, ex_fia2 = ret_fia - ret_ibov, ret_fia2 - ret_ibov
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        cl = GREEN if ret_ibov >= 0 else RED
        st.markdown(metric_card("IBOV", f"<span style='color:{cl}'>{ret_ibov:+.2f}%</span>"), unsafe_allow_html=True)
    with c2:
        cl = GREEN if ret_fia >= 0 else RED
        st.markdown(metric_card("Synta FIA", f"<span style='color:{cl}'>{ret_fia:+.2f}%</span>"), unsafe_allow_html=True)
    with c3:
        cl = GREEN if ret_fia2 >= 0 else RED
        st.markdown(metric_card("Synta FIA II", f"<span style='color:{cl}'>{ret_fia2:+.2f}%</span>"), unsafe_allow_html=True)
    with c4:
        cl = GREEN if ex_fia >= 0 else RED
        st.markdown(metric_card("Excesso FIA", f"<span style='color:{cl}'>{ex_fia:+.2f}%</span>"), unsafe_allow_html=True)
    with c5:
        cl = GREEN if ex_fia2 >= 0 else RED
        st.markdown(metric_card("Excesso FIA II", f"<span style='color:{cl}'>{ex_fia2:+.2f}%</span>"), unsafe_allow_html=True)
    st.markdown("")
    # Cumulative returns
    st.markdown('<div class="tag-section-title">Retorno Acumulado</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Evolução do retorno acumulado (%) de cada fundo e do IBOV desde o inicio do período. "
        "Se a linha do fundo esta acima do IBOV, o fundo esta superando o índice naquele momento."), unsafe_allow_html=True)
    fig_cum = go.Figure()
    ibov_dr = ibov_p.pct_change(fill_method=None).fillna(0)
    ibov_cum = ((1 + ibov_dr).cumprod() - 1) * 100
    fig_cum.add_trace(go.Scatter(x=ibov_cum.index, y=ibov_cum.values, name="IBOV", line=dict(color=TAG_LARANJA, width=2.5)))
    if has_fia and not df_a_fia.empty:
        cota = df_ts_fia.drop_duplicates("data").set_index("data")["valorcota"].sort_index()
        fia_cum = ((1 + cota.pct_change(fill_method=None).fillna(0)).cumprod() - 1) * 100
        fig_cum.add_trace(go.Scatter(x=fia_cum.index, y=fia_cum.values, name="Synta FIA", line=dict(color=TAG_CHART_COLORS[1], width=2)))
    if has_fia2 and not df_a_fia2.empty:
        cota2 = df_ts_fia2.drop_duplicates("data").set_index("data")["valorcota"].sort_index()
        fia2_cum = ((1 + cota2.pct_change(fill_method=None).fillna(0)).cumprod() - 1) * 100
        fig_cum.add_trace(go.Scatter(x=fia2_cum.index, y=fia2_cum.values, name="Synta FIA II", line=dict(color=TAG_CHART_COLORS[2], width=2)))
    fig_cum.add_hline(y=0, line_dash="dot", line_color=TEXT_MUTED, line_width=0.8)
    _chart_layout(fig_cum, "", height=450, y_title="Retorno Acumulado", y_suffix="%")
    st.plotly_chart(fig_cum, width='stretch', key="comp_cum")
    # Excess
    st.markdown('<div class="tag-section-title">Excesso vs IBOV</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Diferenca diaria entre o retorno acumulado do fundo e o do IBOV. "
        "Acima de 0% = fundo superando o IBOV. Abaixo de 0% = fundo ficando para tras. "
        "A area sombreada ajuda a visualizar periodos de outperformance vs underperformance."), unsafe_allow_html=True)
    fig_ex = go.Figure()
    if has_fia and not df_a_fia.empty:
        ci = fia_cum.index.intersection(ibov_cum.index)
        ex_s = fia_cum.reindex(ci) - ibov_cum.reindex(ci)
        fig_ex.add_trace(go.Scatter(x=ex_s.index, y=ex_s.values, name="FIA vs IBOV", line=dict(color=TAG_CHART_COLORS[1], width=2), fill="tozeroy", fillcolor="rgba(92,133,247,0.08)"))
    if has_fia2 and not df_a_fia2.empty:
        ci2 = fia2_cum.index.intersection(ibov_cum.index)
        ex_s2 = fia2_cum.reindex(ci2) - ibov_cum.reindex(ci2)
        fig_ex.add_trace(go.Scatter(x=ex_s2.index, y=ex_s2.values, name="FIA II vs IBOV", line=dict(color=TAG_CHART_COLORS[2], width=2), fill="tozeroy", fillcolor="rgba(107,222,151,0.08)"))
    fig_ex.add_hline(y=0, line_dash="dot", line_color=TEXT_MUTED, line_width=0.8)
    _chart_layout(fig_ex, "", height=400, y_title="Excesso", y_suffix="%")
    st.plotly_chart(fig_ex, width='stretch', key="comp_ex")

# ==============================================================================
# PAGE 5: CARTEIRA EXPLODIDA POR ATIVO
# ==============================================================================
def render_tab_carteira_explodida():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
        <span style="color:{TAG_LARANJA};font-weight:600;">O que é esta página?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        O fundo investe em sub-fundos (Tarpon, Atmos, SPX, etc.) e ETFs (BOVA11, DIVO11).
        Esta pagina <b>"explode"</b> esses investimentos para revelar a <b>exposição real a cada ação individual</b>.<br>
        Ex: Se o fundo tem 15% no SPX Falcon e o SPX tem 5% em PETR4, então a exposição real a PETR4 via SPX = 0.75%.<br>
        <b>Fundos sem dados de composição disponíveis aparecem como "não explodido".</b>
        </span></div>""", unsafe_allow_html=True)

    fundo_sel = st.radio("Fundo", list(FUNDOS_CONFIG.keys()), horizontal=True, key="exp_fundo")

    col_dt, _ = st.columns([2, 4])
    with col_dt:
        ref_date = st.date_input("Data referencia", value=date.today(), format="DD/MM/YYYY", key="exp_dt")

    ref_str = ref_date.strftime("%Y-%m-%d")
    df_exp = explode_fund_to_stocks(fundo_sel, ref_str)

    if df_exp.empty:
        st.warning("Sem dados para explodir. Verifique se existem XMLs para a data selecionada.")
        return

    # Separate equities from non-equity
    equity_types = ["Fundo", "ETF", "Acao", "Fundo>ETF"]
    df_eq = df_exp[df_exp["tipo_origem"].isin(equity_types)].copy()
    df_other = df_exp[~df_exp["tipo_origem"].isin(equity_types)].copy()

    # Aggregate by stock
    if not df_eq.empty:
        df_agg = df_eq.groupby(["ativo", "setor"]).agg(
            exposicao_pct=("exposicao_pct", "sum"),
            n_origens=("origem", "nunique"),
            origens=("origem", lambda x: ", ".join(sorted(set(x)))),
        ).reset_index().sort_values("exposicao_pct", ascending=False)
    else:
        df_agg = pd.DataFrame()

    # Non-equity summary
    total_eq = df_agg["exposicao_pct"].sum() if not df_agg.empty else 0
    total_other = df_other["exposicao_pct"].sum() if not df_other.empty else 0
    n_stocks = len(df_agg) if not df_agg.empty else 0

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("Ações Unicas", f"{n_stocks}"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("Exposição Ações", f"{total_eq:.1f}%"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Outros (RF/Caixa/Fut)", f"{total_other:.1f}%"), unsafe_allow_html=True)
    with c4:
        exploded_funds = df_eq["origem"].nunique() if not df_eq.empty else 0
        st.markdown(metric_card("Fundos Explodidos", f"{exploded_funds}"), unsafe_allow_html=True)

    st.markdown("")

    if not df_agg.empty:
        # ── Top 20 exposures bar chart ──
        st.markdown('<div class="tag-section-title">Top 20 — Maiores Exposicoes Individuais</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> As 20 ações com maior exposição real (% do PL) considerando "
            "todas as vias (direto, via sub-fundos, via ETFs). Passe o mouse para ver por qual fundo/ETF veio."), unsafe_allow_html=True)
        df_top20 = df_agg.head(20).sort_values("exposicao_pct")
        fig_top = go.Figure(go.Bar(
            x=df_top20["exposicao_pct"], y=df_top20["ativo"], orientation="h",
            marker_color=TAG_LARANJA,
            text=[f"{v:.2f}%" for v in df_top20["exposicao_pct"]],
            textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE),
            customdata=df_top20[["setor", "origens"]].values,
            hovertemplate="<b>%{y}</b><br>Exposição: %{x:.2f}%<br>Setor: %{customdata[0]}<br>Via: %{customdata[1]}<extra></extra>",
        ))
        _chart_layout(fig_top, "", height=max(len(df_top20) * 28, 400), y_suffix="%")
        fig_top.update_layout(xaxis_title="Exposicao (% PL)")
        st.plotly_chart(fig_top, width='stretch', key="exp_top20")

        # ── Sector aggregation ──
        st.markdown('<div class="tag-section-title">Exposição por Setor</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> Soma da exposição a ações agrupada por setor. Mostra o perfil setorial "
            "real do fundo apos explodir todos os sub-fundos e ETFs. Compara com o IBOV para entender over/underweight."), unsafe_allow_html=True)
        df_sec = df_agg.groupby("setor").agg(
            exposicao_pct=("exposicao_pct", "sum"),
            n_ativos=("ativo", "count"),
        ).reset_index().sort_values("exposicao_pct", ascending=False)

        col_ch, col_tb = st.columns([3, 2])
        with col_ch:
            df_sec_bar = df_sec.sort_values("exposicao_pct")
            fig_sec = go.Figure(go.Bar(
                x=df_sec_bar["exposicao_pct"], y=df_sec_bar["setor"], orientation="h",
                marker_color=[TAG_CHART_COLORS[i % len(TAG_CHART_COLORS)] for i in range(len(df_sec_bar))],
                text=[f"{v:.1f}%" for v in df_sec_bar["exposicao_pct"]],
                textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE),
            ))
            _chart_layout(fig_sec, "", height=max(len(df_sec_bar) * 28, 350), y_suffix="%")
            fig_sec.update_layout(xaxis_title="Exposicao (% PL)")
            st.plotly_chart(fig_sec, width='stretch', key="exp_sec")

        with col_tb:
            df_sec_show = df_sec[["setor", "exposicao_pct", "n_ativos"]].copy()
            df_sec_show.columns = ["Setor", "Exposicao %", "N Ativos"]
            st.dataframe(df_sec_show.style.format({"Exposicao %": "{:.2f}", "N Ativos": "{:.0f}"}), hide_index=True, height=min(len(df_sec_show) * 38 + 45, 500))

        # ── Treemap by sector > stock ──
        st.markdown('<div class="tag-section-title">Mapa — Exposição por Setor e Ativo</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> Mapa proporcional onde o tamanho de cada retângulo = peso da ação na carteira. "
            "Agrupado por setor. Clique num setor para expandir e ver as ações individuais."), unsafe_allow_html=True)
        df_tm = df_agg[df_agg["exposicao_pct"] > 0.05].head(60)
        if not df_tm.empty:
            sectors = df_tm["setor"].unique().tolist()
            sec_w = df_tm.groupby("setor")["exposicao_pct"].sum()
            labels = sectors + df_tm["ativo"].tolist()
            parents = [""] * len(sectors) + df_tm["setor"].tolist()
            values = [sec_w[s] for s in sectors] + df_tm["exposicao_pct"].tolist()
            texts = [f"<b>{s}</b><br>{sec_w[s]:.1f}%" for s in sectors] + [f"<b>{a}</b><br>{e:.2f}%" for a, e in zip(df_tm["ativo"], df_tm["exposicao_pct"])]
            fig_tm = go.Figure(go.Treemap(labels=labels, parents=parents, values=values,
                marker=dict(colorscale="Viridis", line=dict(width=1, color=TAG_BG_DARK)),
                texttemplate="%{text}", text=texts, textfont=dict(size=10, color=TAG_OFFWHITE), branchvalues="total"))
            fig_tm.update_layout(height=550, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, Tahoma", color=TAG_OFFWHITE))
            st.plotly_chart(fig_tm, width='stretch', key="exp_tm")

        # ── Origin detail: which fund contributes what ──
        st.markdown('<div class="tag-section-title">Detalhe por Origem — Quanto cada sub-fundo/ETF contribui</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> Mostra quanto de exposição a ações vem de cada sub-fundo ou ETF. "
            "Ex: 'Tarpon GT Institucional' contribui X% de exposicao total a acoes. "
            "Fundos que aparecem como 'Direto' são ações compradas diretamente pelo Synta."), unsafe_allow_html=True)
        df_origin = df_eq.groupby("origem").agg(
            exposicao_pct=("exposicao_pct", "sum"),
            n_ativos=("ativo", "nunique"),
        ).reset_index().sort_values("exposicao_pct", ascending=False)

        fig_orig = go.Figure(go.Bar(
            x=df_origin["exposicao_pct"], y=df_origin["origem"], orientation="h",
            marker_color=TAG_CHART_COLORS[1],
            text=[f"{v:.1f}% ({n} ativos)" for v, n in zip(df_origin["exposicao_pct"], df_origin["n_ativos"])],
            textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE),
        ))
        _chart_layout(fig_orig, "", height=max(len(df_origin) * 30, 300), y_suffix="%")
        fig_orig.update_layout(xaxis_title="Exposicao Total (% PL)")
        st.plotly_chart(fig_orig, width='stretch', key="exp_orig")

        # ── Interactive: Stock → Fund origins ──
        st.markdown('<div class="tag-section-title">Explorar Ação — De onde vem a exposição?</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como usar:</b> Selecione uma ação para ver por quais sub-fundos/ETFs o Synta tem exposição a ela. "
            "Mostra o peso que cada via contribui, permitindo entender a concentracao e a diversificacao."), unsafe_allow_html=True)
        # Build per-stock origin data
        stock_list = sorted(df_agg["ativo"].tolist())
        col_sel, col_detail = st.columns([1, 3])
        with col_sel:
            sel_stock = st.selectbox("Selecione uma acao", stock_list, index=0, key="exp_sel_stock")
        df_sel = df_eq[df_eq["ativo"] == sel_stock].copy() if sel_stock else pd.DataFrame()
        with col_detail:
            if not df_sel.empty:
                df_sel_agg = df_sel.groupby("origem").agg(
                    exposicao_pct=("exposicao_pct", "sum"),
                    tipo_origem=("tipo_origem", "first"),
                ).reset_index().sort_values("exposicao_pct", ascending=False)
                total_sel = df_sel_agg["exposicao_pct"].sum()
                setor_sel = df_agg.loc[df_agg["ativo"] == sel_stock, "setor"].iloc[0] if sel_stock in df_agg["ativo"].values else ""
                st.markdown(f"**{sel_stock}** — Setor: {setor_sel} — Exposição total: **{total_sel:.3f}%** do PL")
                fig_sel = go.Figure(go.Bar(
                    x=df_sel_agg["exposicao_pct"], y=df_sel_agg["origem"], orientation="h",
                    marker_color=[TAG_LARANJA if t != "Fundo>ETF" else TAG_CHART_COLORS[1] for t in df_sel_agg["tipo_origem"]],
                    text=[f"{v:.3f}% ({v/total_sel*100:.0f}%)" if total_sel > 0 else f"{v:.3f}%" for v in df_sel_agg["exposicao_pct"]],
                    textposition="outside", textfont=dict(size=10, color=TAG_OFFWHITE),
                    hovertemplate="<b>%{y}</b><br>Exposição: %{x:.3f}%<extra></extra>",
                ))
                _chart_layout(fig_sel, "", height=max(len(df_sel_agg) * 35, 150))
                fig_sel.update_layout(xaxis_title="Exposicao (% PL)", margin=dict(t=10, b=30, l=150, r=80))
                st.plotly_chart(fig_sel, width='stretch', key="exp_sel_chart")
            else:
                st.info("Selecione uma ação na lista ao lado.")

        # ── Interactive: Fund → Stocks held ──
        st.markdown('<div class="tag-section-title">Explorar Fundo — Quais ações ele carrega?</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como usar:</b> Selecione um sub-fundo/ETF para ver todas as ações que ele carrega "
            "e o quanto cada uma contribui para a exposição do Synta. Util para entender a estrategia de cada gestor."), unsafe_allow_html=True)
        origin_list = sorted(df_eq["origem"].unique().tolist())
        col_sel2, col_detail2 = st.columns([1, 3])
        with col_sel2:
            sel_origin = st.selectbox("Selecione um fundo/ETF", origin_list, index=0, key="exp_sel_origin")
        df_sel2 = df_eq[df_eq["origem"] == sel_origin].copy() if sel_origin else pd.DataFrame()
        with col_detail2:
            if not df_sel2.empty:
                df_sel2_agg = df_sel2.groupby(["ativo", "setor"]).agg(
                    exposicao_pct=("exposicao_pct", "sum"),
                ).reset_index().sort_values("exposicao_pct", ascending=False)
                total_sel2 = df_sel2_agg["exposicao_pct"].sum()
                n_ativos_sel2 = len(df_sel2_agg)
                st.markdown(f"**{sel_origin}** — {n_ativos_sel2} ações — Exposição total: **{total_sel2:.2f}%** do PL")
                df_show_sel2 = df_sel2_agg.head(20).sort_values("exposicao_pct")
                fig_sel2 = go.Figure(go.Bar(
                    x=df_show_sel2["exposicao_pct"], y=df_show_sel2["ativo"], orientation="h",
                    marker_color=TAG_CHART_COLORS[2],
                    text=[f"{v:.3f}%" for v in df_show_sel2["exposicao_pct"]],
                    textposition="outside", textfont=dict(size=9, color=TAG_OFFWHITE),
                    customdata=df_show_sel2[["setor"]].values,
                    hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>Exposição: %{x:.3f}%<extra></extra>",
                ))
                _chart_layout(fig_sel2, "", height=max(len(df_show_sel2) * 25, 200))
                fig_sel2.update_layout(xaxis_title="Exposicao (% PL)", margin=dict(t=10, b=30, l=80, r=80))
                st.plotly_chart(fig_sel2, width='stretch', key="exp_sel2_chart")
            else:
                st.info("Selecione um fundo na lista ao lado.")

        # ── Full table ──
        with st.expander(f"Tabela Completa — {len(df_agg)} acoes", expanded=False):
            df_full = df_agg[["ativo", "setor", "exposicao_pct", "origens"]].copy()
            df_full.columns = ["Ativo", "Setor", "Exposicao %", "Origens"]
            st.dataframe(df_full.style.format({"Exposicao %": "{:.3f}"}), hide_index=True, height=600)

    # Show which funds are NOT exploded (only actual fund names, not stocks/options)
    if not df_agg.empty:
        # "Fundo" type but NOT a stock ticker (BR or US) and NOT an option
        mask_fundo = df_exp["tipo_origem"] == "Fundo"
        mask_is_stock = df_exp["ativo"].apply(_is_stock_ticker)
        mask_is_option = df_exp["ativo"].apply(_is_option_ticker)
        df_not_exploded = df_exp[mask_fundo & ~mask_is_stock & ~mask_is_option].copy()
        if not df_not_exploded.empty:
            # Deduplicate by fund name (keep one row per fund)
            df_not_exploded = df_not_exploded.groupby("ativo", as_index=False).agg({"exposicao_pct": "sum"})
            st.markdown(f"""<div style="background:{TAG_BG_CARD};border:1px solid {TAG_LARANJA}40;border-radius:8px;
                padding:12px 16px;margin:10px 0;font-size:0.85rem;">
                <span style="color:{TAG_LARANJA};font-weight:600;">Fundos não explodidos</span><br>
                <span style="color:{TEXT_MUTED};">Os fundos abaixo aparecem como posicao agregada porque não temos dados de composição
                (CVM ou XML) disponíveis. Sua exposição real a ações individuais não esta refletida nos gráficos acima.</span><br><br>
                {"".join(f"<span style='color:{TAG_OFFWHITE};'>• <b>{r['ativo']}</b> — {r['exposicao_pct']:.2f}% do PL</span><br>" for _, r in df_not_exploded.iterrows())}
                </div>""", unsafe_allow_html=True)

    # Non-equity positions
    if not df_other.empty:
        with st.expander("Posicoes Nao-Acoes (RF, Caixa, Futuros, Opcoes)", expanded=False):
            df_oth_show = df_other[["ativo", "setor", "exposicao_pct", "tipo_origem"]].copy()
            df_oth_show.columns = ["Componente", "Classe", "Peso %", "Tipo"]
            st.dataframe(df_oth_show.style.format({"Peso %": "{:.2f}"}), hide_index=True)

    # ── Historical sector evolution (EXPLODED) ──
    st.markdown('<div class="tag-section-title">Evolução Histórica da Composição Setorial (Carteira Explodida)</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Como ler:</b> Área empilhada mostrando como a alocação setorial <b>real</b> do fundo evoluiu ao longo do tempo. "
        "Os sub-fundos sao explodidos em acoes individuais (via CVM) e agrupados por setor. "
        "Mostra a exposição real a cada setor da B3, não apenas as classes genericas.<br>"
        "<span style='color:#FF8853;'>⚠</span> Composição dos sub-fundos via CVM (mensal, defasagem 3-6m). "
        "Os pesos dos componentes no fundo mudam diariamente (XML BNY Mellon)."), unsafe_allow_html=True)

    # Load time series for historical view
    end_hist = ref_date.strftime("%Y-%m-%d")
    start_hist = (ref_date - timedelta(days=180)).strftime("%Y-%m-%d")
    df_hist = load_synta_timeseries(fundo_sel, start_hist, end_hist)

    if not df_hist.empty:
        # Build sector evolution: for each day, distribute component weights to real sectors
        # Use ALL historical compositions so each day uses the closest available snapshot
        subfund_positions_all = load_subfund_positions_all()
        etf_compositions = {}  # cache ETF compositions
        sector_daily = []
        hist_dates = sorted(df_hist["data"].unique())

        # Pre-resolve CNPJ for each component name (avoid repeated lookups)
        _comp_cnpj_cache = {}
        for cnpj, name in SUBFUNDO_NAMES.items():
            _comp_cnpj_cache[name] = cnpj

        for dt in hist_dates:
            day_data = df_hist[df_hist["data"] == dt]
            sector_w = {}  # sector -> weight on this day

            for _, row in day_data.iterrows():
                comp = row["componente"]
                tipo = row["tipo"]
                peso = row["peso_pct"]
                classe = _classificar_componente(comp, tipo)

                if tipo == "Fundo":
                    # Try to explode into stocks — use closest historical composition
                    cnpj_sub = _comp_cnpj_cache.get(comp)
                    if cnpj_sub and not subfund_positions_all.empty:
                        df_snap = _get_subfund_snapshot(subfund_positions_all, cnpj_sub, pd.Timestamp(dt))
                        if not df_snap.empty:
                            total_pct = df_snap["pct_pl"].sum()
                            scale_factor = 100.0 / total_pct if total_pct > 100 else 1.0
                            for _, srow in df_snap.iterrows():
                                ticker = srow["ativo"]
                                pct_in_sub = srow["pct_pl"] * scale_factor
                                expo = peso / 100 * pct_in_sub
                                # Sub-ETF explosion
                                if ticker in ETF_INDEX_MAP:
                                    if ticker not in etf_compositions:
                                        etf_compositions[ticker] = fetch_etf_composition(ticker)
                                    ec = etf_compositions[ticker]
                                    if ec:
                                        for etk, ew in ec.items():
                                            s = classificar_setor(etk)
                                            sector_w[s] = sector_w.get(s, 0) + expo / 100 * ew
                                        continue
                                s = classificar_setor(ticker)
                                sector_w[s] = sector_w.get(s, 0) + expo
                            continue
                    # Can't explode — classify as broad category
                    sector_w[classe] = sector_w.get(classe, 0) + peso

                elif tipo == "Acao/ETF":
                    ticker = comp
                    if ticker in ETF_INDEX_MAP:
                        if ticker not in etf_compositions:
                            etf_compositions[ticker] = fetch_etf_composition(ticker)
                        ec = etf_compositions[ticker]
                        if ec:
                            for etk, ew in ec.items():
                                s = classificar_setor(etk)
                                sector_w[s] = sector_w.get(s, 0) + peso * ew / 100
                            continue
                    s = classificar_setor(ticker)
                    sector_w[s] = sector_w.get(s, 0) + peso
                else:
                    # RF, Caixa, Futuros, Opcoes
                    sector_w[classe] = sector_w.get(classe, 0) + peso

            for s, w in sector_w.items():
                sector_daily.append({"data": dt, "setor": s, "peso": w})

        if sector_daily:
            df_sec_hist = pd.DataFrame(sector_daily)
            pivot_sec = df_sec_hist.pivot_table(index="data", columns="setor", values="peso", aggfunc="sum").fillna(0)
            # Sort columns by average weight
            avg_sec = pivot_sec.mean().sort_values(ascending=False)
            # Keep top 12 sectors, aggregate the rest as "Outros (setores menores)"
            top_secs = avg_sec.head(12).index.tolist()
            other_secs = [c for c in pivot_sec.columns if c not in top_secs]
            pivot_plot_sec = pivot_sec[top_secs].copy()
            if other_secs:
                pivot_plot_sec["Outros (menores)"] = pivot_sec[other_secs].sum(axis=1)

            fig_sec_hist = go.Figure()
            ci_h = TAG_CHART_COLORS * 3
            for i, col in enumerate(pivot_plot_sec.columns):
                fig_sec_hist.add_trace(go.Scatter(
                    x=pivot_plot_sec.index, y=pivot_plot_sec[col], mode="lines",
                    stackgroup="one", name=col, line=dict(width=0.5, color=ci_h[i]),
                    hovertemplate=f"<b>{col}</b><br>%{{x|%d/%m/%Y}}<br>Peso: %{{y:.1f}}%<extra></extra>",
                ))
            _chart_layout(fig_sec_hist, "", height=500, y_title="% PL", y_suffix="%")
            fig_sec_hist.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
            )
            st.plotly_chart(fig_sec_hist, width='stretch', key="exp_hist_sector")

        # ── By broad class (original view) ──
        st.markdown('<div class="tag-section-title">Evolução por Classe (Fundos RV, RF, Caixa, Futuros)</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> Área empilhada mostrando a alocação do fundo por classe genérica "
            "(Fundos RV = sub-fundos equity, Caixa, Renda Fixa, ETFs, Futuros). "
            "Baseado nos XMLs diarios do BNY Mellon."), unsafe_allow_html=True)
        df_hist["classe"] = df_hist.apply(lambda r: _classificar_componente(r["componente"], r["tipo"]), axis=1)
        pivot_classe = df_hist.pivot_table(index="data", columns="classe", values="peso_pct", aggfunc="sum").fillna(0)
        fig_hist = go.Figure()
        ci_h2 = TAG_CHART_COLORS * 3
        for i, col in enumerate(pivot_classe.columns):
            fig_hist.add_trace(go.Scatter(x=pivot_classe.index, y=pivot_classe[col], mode="lines", stackgroup="one", name=col, line=dict(width=0.5, color=ci_h2[i])))
        _chart_layout(fig_hist, "", height=450, y_title="% PL", y_suffix="%")
        st.plotly_chart(fig_hist, width='stretch', key="exp_hist_classe")

        # Stacked area of ALL components over time
        st.markdown('<div class="tag-section-title">Evolução Histórica dos Componentes da Carteira</div>', unsafe_allow_html=True)
        st.markdown(_legenda("<b>Como ler:</b> Área empilhada mostrando o peso (% PL) de <b>todos</b> os componentes individuais do fundo ao longo do tempo. "
            "Os 12 maiores componentes sao exibidos individualmente; os demais sao agrupados em 'Outros'. "
            "Util para acompanhar como a alocação entre sub-fundos, ações, caixa e RF evoluiu."), unsafe_allow_html=True)
        pivot_comp = df_hist.pivot_table(index="data", columns="componente", values="peso_pct", aggfunc="sum").fillna(0)
        avg_comp = pivot_comp.mean().sort_values(ascending=False)
        top_comp = avg_comp.head(12).index.tolist()
        other_comp = [c for c in pivot_comp.columns if c not in top_comp]
        pivot_comp_plot = pivot_comp[top_comp].copy()
        if other_comp:
            pivot_comp_plot["Outros"] = pivot_comp[other_comp].sum(axis=1)
        fig_comp_hist = go.Figure()
        ci_comp = TAG_CHART_COLORS * 3
        for i, col in enumerate(pivot_comp_plot.columns):
            fig_comp_hist.add_trace(go.Scatter(
                x=pivot_comp_plot.index, y=pivot_comp_plot[col], mode="lines",
                stackgroup="one", name=col, line=dict(width=0.5, color=ci_comp[i]),
                hovertemplate=f"<b>{col}</b><br>%{{x|%d/%m/%Y}}<br>Peso: %{{y:.1f}}%<extra></extra>",
            ))
        _chart_layout(fig_comp_hist, "", height=500, y_title="% PL", y_suffix="%")
        fig_comp_hist.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
        )
        st.plotly_chart(fig_comp_hist, width='stretch', key="exp_hist_comp")

    st.markdown(f"""<div class="tag-disclaimer">
        <b>Nota:</b> A explosao usa dados de composição dos sub-fundos obtidos via CVM (mensal) e XMLs
        locais. ETFs sao decompostos usando a composicao atual do indice subjacente via API B3.
        Nem todos os sub-fundos tem dados de composicao disponiveis. Fundos sem dados aparecem como
        posicao agregada. BNY ARX Liquidez e classificado como Caixa.
    </div>""", unsafe_allow_html=True)

# ==============================================================================
# PAGE 6: DESEMPENHO INDIVIDUAL DOS ATIVOS
# ==============================================================================
@st.cache_data(ttl=3600, show_spinner="Buscando cotas dos sub-fundos...")
def _fetch_fund_quotas(cnpjs: tuple, start: str, end: str) -> pd.DataFrame:
    """Fetch daily quotas for sub-funds from CVM inf_diario cache."""
    frames = []
    cache_dir = CARTEIRA_RV_CACHE

    # --- Cloud mode: read from pre-exported parquet ---
    if not os.path.isdir(cache_dir):
        pq_path = os.path.join(DATA_DIR, "fund_quotas.parquet")
        if os.path.exists(pq_path):
            df = pd.read_parquet(pq_path)
            df["data"] = pd.to_datetime(df["data"])
            cnpj_set = set(cnpjs)
            df = df[df["cnpj_raw"].isin(cnpj_set)]
            df = df[(df["data"] >= pd.Timestamp(start)) & (df["data"] <= pd.Timestamp(end))]
            return df.sort_values("data").drop_duplicates(subset=["data", "cnpj_raw"], keep="last")
        return pd.DataFrame()
    inf_files = sorted(glob.glob(os.path.join(cache_dir, "cvm_inf_diario_*.parquet")))
    cnpj_set = set(cnpjs)
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    for fpath in inf_files:
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            continue
        # Column names vary: cnpj_norm (filtered), CNPJ_FUNDO_CLASSE, CNPJ_FUNDO
        cnpj_col = None
        for c in ["cnpj_norm", "CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"]:
            if c in df.columns:
                cnpj_col = c
                break
        dt_col = "DT_COMPTC"
        vl_col = "VL_QUOTA"
        if cnpj_col is None or dt_col not in df.columns or vl_col not in df.columns:
            continue

        # cnpj_norm is already unformatted 14-digit; formatted CNPJs need cleaning
        if cnpj_col == "cnpj_norm":
            mask = df[cnpj_col].isin(cnpj_set)
        else:
            # Format our CNPJs to match xx.xxx.xxx/xxxx-xx
            def _fmt(c):
                c = c.zfill(14)
                return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}"
            fmt_map = {_fmt(c): c for c in cnpj_set}
            mask = df[cnpj_col].isin(fmt_map.keys())

        df_f = df[mask].copy()
        if df_f.empty:
            continue
        df_f["data"] = pd.to_datetime(df_f[dt_col])
        df_f = df_f[(df_f["data"] >= start_dt) & (df_f["data"] <= end_dt)]
        if df_f.empty:
            continue
        if cnpj_col == "cnpj_norm":
            df_f["cnpj_raw"] = df_f[cnpj_col]
        else:
            df_f["cnpj_raw"] = df_f[cnpj_col].map(fmt_map)
        df_f["nome"] = df_f["cnpj_raw"].map(SUBFUNDO_NAMES)
        df_f["quota"] = pd.to_numeric(df_f[vl_col], errors="coerce")
        frames.append(df_f[["data", "cnpj_raw", "nome", "quota"]].dropna())

    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values("data").drop_duplicates(subset=["data", "cnpj_raw"], keep="last")
    return result


def render_tab_desempenho_individual():
    st.markdown(f"""<div style="background:linear-gradient(135deg,{TAG_BG_CARD} 0%,{TAG_BG_CARD_ALT} 100%);
        border:1px solid {TAG_VERMELHO}30;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
        <span style="color:{TAG_LARANJA};font-weight:600;">O que é esta página?</span><br>
        <span style="color:{TAG_OFFWHITE};font-size:0.88rem;">
        Compara o desempenho (retorno acumulado) dos <b>sub-fundos</b>, do <b>próprio Synta FIA / FIA II</b>,
        e de <b>ativos diretos</b> (ações/ETFs na carteira) contra o <b>IBOV</b>.<br>
        <b>Métricas:</b> Retorno acumulado, volatilidade anualizada, Sharpe, max drawdown, beta vs IBOV, Ulcer Index.
        </span></div>""", unsafe_allow_html=True)

    dt_inicio, dt_fim = period_selector("desemp")

    # Fetch IBOV prices
    start_fetch = (dt_inicio - timedelta(days=10)).strftime("%Y-%m-%d")
    end_str = (dt_fim + timedelta(days=1)).strftime("%Y-%m-%d")

    # ----- SECTION 1: Sub-fund performance vs IBOV -----
    st.markdown('<div class="tag-section-title">Retorno Acumulado dos Sub-Fundos vs IBOV</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Cada linha mostra o retorno acumulado de um sub-fundo investido pelo Synta. "
        "As linhas <b>grossas</b> são o <b>Synta FIA</b> e <b>Synta FIA II</b> (o fundo em si). "
        "A linha <b>tracejada branca</b> e o IBOV (benchmark). Sub-fundos acima do IBOV estao ganhando; abaixo, perdendo. "
        "Por padrao mostra todos os sub-fundos + IBOV. Use o seletor para filtrar."), unsafe_allow_html=True)

    # Select which Synta fund to analyze
    fundo_key = st.radio("Fundo base", list(FUNDOS_CONFIG.keys()), index=0, horizontal=True, key="desemp_fundo")

    # Load positions to get sub-fund CNPJs + direct positions
    config = FUNDOS_CONFIG[fundo_key]
    prefix = config["xml_prefix"]
    ref_dt = dt_fim
    parsed = None

    # --- Cloud mode: reconstruct from parquet ---
    if not HAS_LOCAL_XML and HAS_PARQUET_DATA:
        safe_name = fundo_key.lower().replace(" ", "_")
        parquet_path = os.path.join(DATA_DIR, f"timeseries_{safe_name}.parquet")
        if os.path.exists(parquet_path):
            df_pq = pd.read_parquet(parquet_path)
            df_pq["data"] = pd.to_datetime(df_pq["data"])
            df_pq = df_pq[df_pq["data"].dt.date <= ref_dt]
            if not df_pq.empty:
                latest_date = df_pq["data"].max()
                df_snap = df_pq[df_pq["data"] == latest_date]
                posicoes = []
                for _, row in df_snap.iterrows():
                    pos = {"componente": row["componente"], "tipo": row["tipo"],
                           "valor": row["valor"], "peso_pct": row["peso_pct"]}
                    if "cnpj" in row and pd.notna(row.get("cnpj")):
                        pos["cnpj"] = row["cnpj"]
                    posicoes.append(pos)
                parsed = {"posicoes": posicoes}

    # --- Local mode: parse XML ---
    if parsed is None and HAS_LOCAL_XML:
        xml_path = None
        for folder_name in sorted(os.listdir(XML_BASE), reverse=True):
            try:
                folder_date = datetime.strptime(folder_name, "%Y%m%d").date()
            except ValueError:
                continue
            if folder_date <= ref_dt:
                xml_path = _find_synta_xml(folder_name, prefix)
                if xml_path:
                    break
        if xml_path:
            parsed = parse_synta_xml(xml_path)

    subfund_cnpjs = []
    direct_tickers = []  # direct stock/ETF holdings in the fund
    if parsed and parsed.get("posicoes"):
        for pos in parsed["posicoes"]:
            if pos["tipo"] == "Fundo":
                cnpj_sub = pos.get("cnpj", "")
                if cnpj_sub:
                    subfund_cnpjs.append(cnpj_sub)
            elif pos["tipo"] == "Acao/ETF":
                tk = pos.get("componente", "")
                if tk and _is_stock_ticker(tk) and not _is_option_ticker(tk):
                    direct_tickers.append(tk)

    if not subfund_cnpjs:
        st.warning("Sem dados de sub-fundos para o período selecionado.")
        return

    # Fetch fund quotas from CVM — sub-funds + Synta FIA + Synta FIA II
    synta_cnpjs = [cfg["cnpj"] for cfg in FUNDOS_CONFIG.values()]
    all_cnpjs_to_fetch = list(set(subfund_cnpjs + synta_cnpjs))
    quota_df = _fetch_fund_quotas(tuple(all_cnpjs_to_fetch), dt_inicio.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d"))

    # Fetch IBOV + direct stock/ETF prices
    direct_sa = tuple(f"{tk}.SA" for tk in direct_tickers) if direct_tickers else tuple()
    ibov_prices = fetch_prices(direct_sa, start_fetch, end_str)
    ibov_series = pd.Series(dtype=float)
    if not ibov_prices.empty and "^BVSP" in ibov_prices.columns:
        ibov_series = ibov_prices["^BVSP"].dropna()

    # Build cumulative return series for each fund
    fund_returns = {}
    synta_names = {}  # track Synta FIA/FIA II names for special styling
    current_portfolio = set()  # track names of current portfolio holdings for default selection
    if not quota_df.empty:
        # Sub-funds first
        for cnpj in subfund_cnpjs:
            nome = SUBFUNDO_NAMES.get(cnpj, f"Fundo {cnpj[:8]}")
            df_f = quota_df[quota_df["cnpj_raw"] == cnpj].set_index("data")["quota"].sort_index()
            if len(df_f) < 2:
                continue
            df_f = df_f[df_f.index >= pd.Timestamp(dt_inicio)]
            if len(df_f) < 2:
                continue
            cum_ret = (df_f / df_f.iloc[0] - 1) * 100
            fund_returns[nome] = cum_ret
            current_portfolio.add(nome)

        # Synta FIA and Synta FIA II as additional lines
        for fk, cfg in FUNDOS_CONFIG.items():
            cnpj_synta = cfg["cnpj"]
            df_s = quota_df[quota_df["cnpj_raw"] == cnpj_synta].set_index("data")["quota"].sort_index()
            if len(df_s) < 2:
                continue
            df_s = df_s[df_s.index >= pd.Timestamp(dt_inicio)]
            if len(df_s) < 2:
                continue
            cum_ret = (df_s / df_s.iloc[0] - 1) * 100
            fund_returns[fk] = cum_ret
            synta_names[fk] = True

    # Direct stock/ETF holdings (e.g. BOVA11, SBSP3, LVOL11)
    direct_holdings_in_chart = []
    tickers_resolved = set()
    if direct_tickers and not ibov_prices.empty:
        for tk in direct_tickers:
            sa = f"{tk}.SA"
            if sa in ibov_prices.columns:
                p = ibov_prices[sa].dropna()
                p = p[p.index >= pd.Timestamp(dt_inicio)]
                if len(p) >= 2:
                    cum_ret = (p / p.iloc[0] - 1) * 100
                    label = f"{tk} (direto)"
                    fund_returns[label] = cum_ret
                    direct_holdings_in_chart.append(label)
                    tickers_resolved.add(tk)

    # Fallback for tickers without yfinance data: use PU from fund timeseries
    missing_tickers = [tk for tk in direct_tickers if tk not in tickers_resolved]
    if missing_tickers:
        ts_df = load_synta_timeseries(fundo_key, start_fetch, end_str)
        if not ts_df.empty:
            ts_df["data"] = pd.to_datetime(ts_df["data"])
            for tk in missing_tickers:
                tk_data = ts_df[(ts_df["componente"] == tk) & (ts_df["tipo"] == "Ação/ETF")]
                if tk_data.empty:
                    continue
                tk_data = tk_data[["data", "pu"]].dropna(subset=["pu"])
                tk_data = tk_data[tk_data["pu"] > 0].drop_duplicates("data").set_index("data").sort_index()
                tk_data = tk_data[tk_data.index >= pd.Timestamp(dt_inicio)]
                if len(tk_data) >= 2:
                    cum_ret = (tk_data["pu"] / tk_data["pu"].iloc[0] - 1) * 100
                    label = f"{tk} (direto)"
                    fund_returns[label] = cum_ret
                    direct_holdings_in_chart.append(label)

    # Other asset types: RF, Futuros, Opcoes — use PU or vlajuste from timeseries
    other_holdings_in_chart = []
    ts_all = load_synta_timeseries(fundo_key, start_fetch, end_str)
    if not ts_all.empty:
        ts_all["data"] = pd.to_datetime(ts_all["data"])
        ts_period = ts_all[ts_all["data"] >= pd.Timestamp(dt_inicio)]
        # Get PL per day for contribution-based returns (futuros)
        pl_daily = ts_period.groupby("data")["patliq"].first().sort_index() if "patliq" in ts_period.columns else pd.Series(dtype=float)

        for tipo_other in ["RF", "Futuro", "Opcao Futuro", "Opcao"]:
            tipo_data = ts_period[ts_period["tipo"] == tipo_other]
            if tipo_data.empty:
                continue

            if tipo_other == "RF":
                # RF has PU — build return from PU like a bond fund
                for comp in tipo_data["componente"].unique():
                    cd = tipo_data[tipo_data["componente"] == comp]
                    cd_pu = cd[["data", "pu"]].dropna(subset=["pu"])
                    cd_pu = cd_pu[cd_pu["pu"] > 0].drop_duplicates("data").set_index("data").sort_index()
                    cd_pu = cd_pu[cd_pu.index >= pd.Timestamp(dt_inicio)]
                    if len(cd_pu) >= 2:
                        cum_ret = (cd_pu["pu"] / cd_pu["pu"].iloc[0] - 1) * 100
                        fund_returns[comp] = cum_ret
                        other_holdings_in_chart.append(comp)

            elif tipo_other in ("Futuro",):
                # Futuros: aggregate all contracts, use vlajuste/PL for daily contribution
                if "vlajuste" in tipo_data.columns and not pl_daily.empty:
                    aj_daily = tipo_data.groupby("data")["vlajuste"].sum().sort_index()
                    aj_daily = aj_daily[aj_daily.index >= pd.Timestamp(dt_inicio)]
                    # Contribution = vlajuste / PL
                    common_dates = aj_daily.index.intersection(pl_daily.index)
                    if len(common_dates) >= 2:
                        contrib = aj_daily.loc[common_dates] / pl_daily.loc[common_dates]
                        cum_contrib = (1 + contrib).cumprod()
                        cum_ret = (cum_contrib / cum_contrib.iloc[0] - 1) * 100
                        label = "Futuros (WIN)"
                        fund_returns[label] = cum_ret
                        other_holdings_in_chart.append(label)

            elif tipo_other in ("Opcao Futuro", "Opcao"):
                # Opcoes: use change in total valor / PL
                if not pl_daily.empty:
                    val_daily = tipo_data.groupby("data")["valor"].sum().sort_index()
                    val_daily = val_daily[val_daily.index >= pd.Timestamp(dt_inicio)]
                    if len(val_daily) >= 2:
                        delta_val = val_daily.diff().fillna(0)
                        common_dates = delta_val.index.intersection(pl_daily.index)
                        if len(common_dates) >= 2:
                            contrib = delta_val.loc[common_dates] / pl_daily.loc[common_dates]
                            cum_contrib = (1 + contrib).cumprod()
                            cum_ret = (cum_contrib / cum_contrib.iloc[0] - 1) * 100
                            label = f"Opcoes ({tipo_other.split()[-1]})" if "Futuro" in tipo_other else "Opcoes"
                            fund_returns[label] = cum_ret
                            other_holdings_in_chart.append(label)

    # IBOV cumulative
    if not ibov_series.empty:
        ibov_period = ibov_series[ibov_series.index >= pd.Timestamp(dt_inicio)]
        if len(ibov_period) >= 2:
            ibov_cum = (ibov_period / ibov_period.iloc[0] - 1) * 100
            fund_returns["IBOVESPA"] = ibov_cum

    if not fund_returns:
        st.warning("Sem dados de cotas disponíveis para o período.")
        return

    # Multiselect for funds to show — default to ALL current portfolio holdings + benchmarks
    current_portfolio.update(direct_holdings_in_chart)
    current_portfolio.update(other_holdings_in_chart)
    current_portfolio.update(synta_names.keys())
    if "IBOVESPA" in fund_returns:
        current_portfolio.add("IBOVESPA")
    all_names = list(fund_returns.keys())
    default_sel = [n for n in all_names if n in current_portfolio]
    if not default_sel:
        default_sel = all_names
    # Use dynamic key per fund so switching funds resets the multiselect to defaults
    ms_key = f"desemp_sel_{fundo_key.replace(' ', '_')}"
    selected_funds = st.multiselect("Selecione fundos para exibir", all_names, default=default_sel, key=ms_key)

    if not selected_funds:
        st.info("Selecione ao menos um fundo.")
        return

    # Cumulative return chart
    fig_cum = go.Figure()
    color_idx = 0
    for name in selected_funds:
        series = fund_returns[name]
        is_bench = name == "IBOVESPA"
        is_synta = name in synta_names
        is_direct = name in direct_holdings_in_chart
        is_other = name in other_holdings_in_chart
        if is_bench:
            color = "#FFFFFF"
            width = 3
            dash = "dash"
        elif is_synta:
            color = TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA
            width = 3
            dash = "solid"
        elif is_direct:
            color = "#00CED1"  # cyan for direct holdings
            width = 2
            dash = "dot"
        elif is_other:
            color = "#FFD700"  # gold for RF/Futuros/Opcoes
            width = 2
            dash = "dashdot"
        else:
            color = TAG_CHART_COLORS[color_idx % len(TAG_CHART_COLORS)]
            width = 1.8
            dash = "solid"
            color_idx += 1
        fig_cum.add_trace(go.Scatter(
            x=series.index, y=series.values, mode="lines",
            name=name,
            line=dict(width=width, color=color, dash=dash),
            hovertemplate=f"<b>{name}</b><br>%{{x|%d/%m/%Y}}<br>Retorno: %{{y:+.2f}}%<extra></extra>",
        ))
    _chart_layout(fig_cum, "", height=500, y_title="Retorno Acumulado (%)", y_suffix="%")
    fig_cum.update_layout(hovermode="x unified")
    st.plotly_chart(fig_cum, width='stretch', key="desemp_cum")

    # ----- Metrics Table -----
    st.markdown('<div class="tag-section-title">Métricas de Performance</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Ret.Acum</b> = Retorno total no período. "
        "<b>Vol.Anual</b> = Volatilidade anualizada (risco). "
        "<b>Sharpe</b> = Retorno / Risco (quanto maior, melhor). "
        "<b>Max DD</b> = Maior queda do pico ao vale (quanto menor em modulo, melhor). "
        "<b>Beta</b> = Sensibilidade ao IBOV (>1 = mais volátil que IBOV). "
        "<b>Excesso</b> = Retorno acumulado - Retorno IBOV."), unsafe_allow_html=True)

    # Compute metrics
    ibov_ret_total = 0
    ibov_daily_rets = pd.Series(dtype=float)
    if "IBOVESPA" in fund_returns:
        s = fund_returns["IBOVESPA"]
        ibov_ret_total = s.iloc[-1] if len(s) > 0 else 0
        ibov_daily_rets = s.diff() / 100  # approximate daily returns

    metrics_rows = []
    for name in selected_funds:
        s = fund_returns[name]
        if len(s) < 2:
            continue
        ret_total = s.iloc[-1]
        daily_rets = s.diff() / 100  # rough daily
        daily_rets = daily_rets.dropna()

        vol_annual = daily_rets.std() * np.sqrt(252) * 100 if len(daily_rets) > 5 else 0
        # Simplified Sharpe: (ret_annual) / vol_annual
        n_days = len(daily_rets)
        ret_annual = ((1 + ret_total / 100) ** (252 / max(n_days, 1)) - 1) * 100
        sharpe_simple = ret_annual / vol_annual if vol_annual > 0 else 0

        # Max drawdown
        cum_vals = (1 + daily_rets).cumprod()
        running_max = cum_vals.cummax()
        drawdown = (cum_vals / running_max - 1) * 100
        max_dd = drawdown.min()

        # Beta
        beta = 0
        if not ibov_daily_rets.empty and name != "IBOVESPA":
            aligned = pd.DataFrame({"fund": daily_rets, "ibov": ibov_daily_rets}).dropna()
            if len(aligned) > 10:
                cov_matrix = np.cov(aligned["fund"], aligned["ibov"])
                if cov_matrix[1, 1] > 0:
                    beta = cov_matrix[0, 1] / cov_matrix[1, 1]

        excesso = ret_total - ibov_ret_total

        metrics_rows.append({
            "Fundo": name,
            "Ret.Acum (%)": ret_total,
            "Ret.Anual (%)": ret_annual,
            "Vol.Anual (%)": vol_annual,
            "Sharpe": sharpe_simple,
            "Max DD (%)": max_dd,
            "Beta": beta,
            "Excesso (%)": excesso,
        })

    if metrics_rows:
        df_metrics = pd.DataFrame(metrics_rows).sort_values("Ret.Acum (%)", ascending=False)
        st.dataframe(df_metrics.style.format({
            "Ret.Acum (%)": "{:+.2f}", "Ret.Anual (%)": "{:+.2f}",
            "Vol.Anual (%)": "{:.2f}", "Sharpe": "{:.2f}",
            "Max DD (%)": "{:.2f}", "Beta": "{:.2f}", "Excesso (%)": "{:+.2f}",
        }).map(lambda v: f"color: {GREEN}" if isinstance(v, (int, float)) and v > 0 else f"color: {RED}" if isinstance(v, (int, float)) and v < 0 else "", subset=["Ret.Acum (%)", "Excesso (%)"]),
        hide_index=True, height=min(len(df_metrics) * 38 + 45, 600))

    # ----- Drawdown chart -----
    st.markdown('<div class="tag-section-title">Drawdown</div>', unsafe_allow_html=True)
    st.markdown(_legenda("<b>Como ler:</b> Mostra a queda percentual de cada fundo/ativo em relação ao seu pico anterior. "
        "Quanto mais profundo o vale, maior a perda temporaria. Um bom fundo recupera rapido (vale raso e curto)."), unsafe_allow_html=True)
    fig_dd = go.Figure()
    color_idx = 0
    for name in selected_funds:
        s = fund_returns[name]
        daily_rets = s.diff() / 100
        daily_rets = daily_rets.dropna()
        if len(daily_rets) < 2:
            continue
        cum_vals = (1 + daily_rets).cumprod()
        running_max = cum_vals.cummax()
        drawdown_s = (cum_vals / running_max - 1) * 100
        is_bench = name == "IBOVESPA"
        is_synta = name in synta_names
        is_direct = name in direct_holdings_in_chart
        is_other = name in other_holdings_in_chart
        if is_bench:
            color = "#FFFFFF"; width = 2; dash = "dash"
        elif is_synta:
            color = TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA; width = 2.5; dash = "solid"
        elif is_direct:
            color = "#00CED1"; width = 1.5; dash = "dot"
        elif is_other:
            color = "#FFD700"; width = 1.5; dash = "dashdot"
        else:
            color = TAG_CHART_COLORS[color_idx % len(TAG_CHART_COLORS)]; width = 1.5; dash = "solid"
            color_idx += 1
        fig_dd.add_trace(go.Scatter(
            x=drawdown_s.index, y=drawdown_s.values, mode="lines",
            name=name, line=dict(width=width, color=color, dash=dash),
        ))
    _chart_layout(fig_dd, "", height=400, y_title="Drawdown (%)", y_suffix="%")
    fig_dd.update_layout(hovermode="x unified")
    st.plotly_chart(fig_dd, width='stretch', key="desemp_dd")

    # ----- SECTION 2: Scatter Risk vs Return -----
    st.markdown('<div class="tag-section-title">Risco x Retorno</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Como ler:</b> Cada ponto = um sub-fundo ou o próprio Synta. "
        "<b>Eixo X</b> = Volatilidade anualizada (risco). <b>Eixo Y</b> = Retorno acumulado. "
        "O ideal e estar no <b>canto superior esquerdo</b> (alto retorno, baixo risco). "
        "O IBOV aparece como referência."), unsafe_allow_html=True)

    if metrics_rows:
        df_scatter = pd.DataFrame(metrics_rows)
        fig_rr = go.Figure()
        color_idx = 0
        for _, row in df_scatter.iterrows():
            is_bench = row["Fundo"] == "IBOVESPA"
            is_synta = row["Fundo"] in synta_names
            is_direct = row["Fundo"] in direct_holdings_in_chart
            is_other = row["Fundo"] in other_holdings_in_chart
            if is_bench:
                color = "#FFFFFF"; symbol = "star"; sz = 16
            elif is_synta:
                color = TAG_VERMELHO_LIGHT if "FIA II" in row["Fundo"] else TAG_LARANJA; symbol = "diamond"; sz = 14
            elif is_direct:
                color = "#00CED1"; symbol = "square"; sz = 10
            elif is_other:
                color = "#FFD700"; symbol = "triangle-up"; sz = 10
            else:
                color = TAG_CHART_COLORS[color_idx % len(TAG_CHART_COLORS)]; symbol = "circle"; sz = 10
                color_idx += 1
            fig_rr.add_trace(go.Scatter(
                x=[row["Vol.Anual (%)"]], y=[row["Ret.Acum (%)"]],
                mode="markers+text", text=[row["Fundo"]],
                textposition="top center", textfont=dict(size=9, color=TAG_OFFWHITE),
                marker=dict(size=sz, color=color, symbol=symbol, line=dict(width=1, color=TAG_OFFWHITE)),
                showlegend=False,
                hovertemplate=f"<b>{row['Fundo']}</b><br>Vol: {row['Vol.Anual (%)']:.1f}%<br>Ret: {row['Ret.Acum (%)']:+.1f}%<extra></extra>",
            ))
        _chart_layout(fig_rr, "", height=450, y_title="Retorno Acumulado (%)", y_suffix="%")
        fig_rr.update_layout(xaxis_title="Volatilidade Anualizada (%)")
        st.plotly_chart(fig_rr, width='stretch', key="desemp_rr")

    # ----- Retorno x Ulcer Index Scatter -----
    st.markdown('<div class="tag-section-title">Retorno x Ulcer Index</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Como ler:</b> Cada ponto = um fundo. "
        "<b>Eixo X</b> = Ulcer Index (risco por drawdown — menor = melhor). "
        "<b>Eixo Y</b> = Retorno acumulado. "
        "O ideal e estar no <b>canto superior esquerdo</b> (alto retorno, baixo Ulcer Index). "
        "Fundos com baixo Ulcer e alto retorno tem melhor <b>UPI</b> (Ulcer Performance Index)."),
        unsafe_allow_html=True)

    if metrics_rows:
        # Compute Ulcer Index for each fund
        ulcer_data = []
        for name in selected_funds:
            if name not in fund_returns:
                continue
            s = fund_returns[name]
            if len(s) < 10:
                continue
            cum_max = s.cummax()
            dd_pct = s - cum_max
            ulcer_idx = np.sqrt((dd_pct ** 2).mean())
            ulcer_data.append({"Fundo": name, "Ulcer Index": ulcer_idx})

        if ulcer_data:
            df_ulcer_scatter = pd.DataFrame(ulcer_data)
            df_met_tmp = pd.DataFrame(metrics_rows)
            df_ulcer_scatter = df_ulcer_scatter.merge(df_met_tmp[["Fundo", "Ret.Acum (%)"]], on="Fundo", how="inner")
            if not df_ulcer_scatter.empty and len(df_ulcer_scatter) >= 2:
                fig_ru = go.Figure()
                color_idx_ru = 0
                for _, row in df_ulcer_scatter.iterrows():
                    is_bench = row["Fundo"] == "IBOVESPA"
                    is_synta = row["Fundo"] in synta_names
                    is_direct = row["Fundo"] in direct_holdings_in_chart
                    if is_bench:
                        color = "#FFFFFF"; symbol = "star"; sz = 16
                    elif is_synta:
                        color = TAG_VERMELHO_LIGHT if "FIA II" in row["Fundo"] else TAG_LARANJA; symbol = "diamond"; sz = 14
                    elif is_direct:
                        color = "#00CED1"; symbol = "square"; sz = 10
                    else:
                        color = TAG_CHART_COLORS[color_idx_ru % len(TAG_CHART_COLORS)]; symbol = "circle"; sz = 10
                        color_idx_ru += 1
                    upi = row["Ret.Acum (%)"] / row["Ulcer Index"] if row["Ulcer Index"] > 0.01 else 0
                    fig_ru.add_trace(go.Scatter(
                        x=[row["Ulcer Index"]], y=[row["Ret.Acum (%)"]],
                        mode="markers+text", text=[row["Fundo"]],
                        textposition="top center", textfont=dict(size=9, color=TAG_OFFWHITE),
                        marker=dict(size=sz, color=color, symbol=symbol, line=dict(width=1, color=TAG_OFFWHITE)),
                        showlegend=False,
                        hovertemplate=f"<b>{row['Fundo']}</b><br>Ulcer: {row['Ulcer Index']:.3f}<br>Ret: {row['Ret.Acum (%)']:+.1f}%<br>UPI: {upi:.1f}<extra></extra>",
                    ))
                _chart_layout(fig_ru, "", height=450, y_title="Retorno Acumulado (%)", y_suffix="%")
                fig_ru.update_layout(xaxis_title="Ulcer Index")
                st.plotly_chart(fig_ru, width='stretch', key="desemp_ret_ulcer")

    # ----- SECTION 3: Rolling Analytics -----
    st.markdown("---")
    st.markdown('<div class="tag-section-title">Analise Rolling (Janela Movel)</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Como ler:</b> Gráficos de janela móvel mostram como as métricas evoluem ao longo do tempo. "
        "Util para identificar mudancas de regime — um fundo que era defensivo e ficou agressivo, ou vice-versa. "
        "Selecione a janela em dias uteis (63 ≈ 3 meses, 126 ≈ 6 meses, 252 ≈ 1 ano)."), unsafe_allow_html=True)

    # Rolling window selector
    janela_du = st.select_slider("Janela (dias uteis)", options=[21, 42, 63, 126, 252], value=21, key="desemp_janela")

    # Build daily returns DataFrame for rolling calculations
    fund_daily_rets = {}
    for name in selected_funds:
        s = fund_returns[name]
        if len(s) > 2:
            fund_daily_rets[name] = s.diff() / 100  # approximate daily returns

    if len(fund_daily_rets) >= 2 and "IBOVESPA" in fund_daily_rets:
        ibov_dr = fund_daily_rets["IBOVESPA"].dropna()

        # Helper to get line style per fund
        def _line_style(name, color_counter=[0]):
            is_bench = name == "IBOVESPA"
            is_synta = name in synta_names
            is_direct = name in direct_holdings_in_chart
            if is_bench:
                return dict(width=2.5, color="#FFFFFF", dash="dash")
            elif is_synta:
                return dict(width=2.5, color=TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA, dash="solid")
            elif is_direct:
                return dict(width=1.8, color="#00CED1", dash="dot")
            else:
                c = TAG_CHART_COLORS[color_counter[0] % len(TAG_CHART_COLORS)]
                color_counter[0] += 1
                return dict(width=1.8, color=c, dash="solid")

        # ── Rolling Beta vs IBOV ──
        st.markdown(f'<div class="tag-section-title">Rolling Beta vs IBOV ({janela_du}du)</div>', unsafe_allow_html=True)
        st.markdown(_legenda(
            "<b>Beta</b> mede a sensibilidade ao IBOV. Beta > 1 = mais volátil que o índice; Beta < 1 = mais defensivo. "
            "A linha tracejada em 1.0 indica beta neutro."), unsafe_allow_html=True)
        fig_rbeta = go.Figure()
        color_counter_beta = [0]
        for name in selected_funds:
            if name == "IBOVESPA" or name not in fund_daily_rets:
                continue
            fund_dr = fund_daily_rets[name].dropna()
            aligned = pd.DataFrame({"fund": fund_dr, "ibov": ibov_dr}).dropna()
            if len(aligned) < janela_du + 5:
                continue
            roll_cov = aligned["fund"].rolling(janela_du).cov(aligned["ibov"])
            roll_var = aligned["ibov"].rolling(janela_du).var()
            roll_beta = (roll_cov / roll_var).dropna().clip(0, 3)
            is_synta = name in synta_names
            is_direct = name in direct_holdings_in_chart
            if is_synta:
                ls = dict(width=2.5, color=TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA, dash="solid")
            elif is_direct:
                ls = dict(width=1.8, color="#00CED1", dash="dot")
            else:
                ls = dict(width=2, color=TAG_CHART_COLORS[color_counter_beta[0] % len(TAG_CHART_COLORS)], dash="solid")
                color_counter_beta[0] += 1
            fig_rbeta.add_trace(go.Scatter(
                x=roll_beta.index, y=roll_beta.values, mode="lines",
                name=name, line=ls,
                hovertemplate=f"<b>{name}</b><br>%{{x|%d/%m/%Y}}<br>Beta: %{{y:.2f}}<extra></extra>",
            ))
        fig_rbeta.add_hline(y=1.0, line_dash="dash", line_color="rgba(230,228,219,0.3)", line_width=1)
        _chart_layout(fig_rbeta, "", height=380, y_title="Beta")
        fig_rbeta.update_layout(hovermode="x unified")
        st.plotly_chart(fig_rbeta, width='stretch', key="desemp_rbeta")

        # ── Rolling Sharpe ──
        st.markdown(f'<div class="tag-section-title">Rolling Sharpe ({janela_du}du)</div>', unsafe_allow_html=True)
        st.markdown(_legenda(
            "<b>Sharpe</b> = retorno ajustado ao risco na janela móvel. Quanto maior, melhor. "
            "Sharpe > 1 e considerado bom; > 2 e excelente."), unsafe_allow_html=True)
        fig_rsharpe = go.Figure()
        color_counter_sharpe = [0]
        for name in selected_funds:
            if name not in fund_daily_rets:
                continue
            dr = fund_daily_rets[name].dropna()
            if len(dr) < janela_du + 5:
                continue
            roll_ret_ann = dr.rolling(janela_du).mean() * 252
            roll_vol_ann = dr.rolling(janela_du).std() * np.sqrt(252)
            roll_sharpe = (roll_ret_ann / roll_vol_ann).replace([np.inf, -np.inf], np.nan).dropna()
            roll_sharpe = roll_sharpe.clip(-10, 10)  # clip extreme values
            is_bench = name == "IBOVESPA"
            is_synta = name in synta_names
            is_direct = name in direct_holdings_in_chart
            if is_bench:
                ls = dict(width=2.5, color="#FFFFFF", dash="dash")
            elif is_synta:
                ls = dict(width=2.5, color=TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA, dash="solid")
            elif is_direct:
                ls = dict(width=1.8, color="#00CED1", dash="dot")
            else:
                ls = dict(width=1.8, color=TAG_CHART_COLORS[color_counter_sharpe[0] % len(TAG_CHART_COLORS)], dash="solid")
                color_counter_sharpe[0] += 1
            fig_rsharpe.add_trace(go.Scatter(
                x=roll_sharpe.index, y=roll_sharpe.values, mode="lines",
                name=name, line=ls,
                hovertemplate=f"<b>{name}</b><br>%{{x|%d/%m/%Y}}<br>Sharpe: %{{y:.2f}}<extra></extra>",
            ))
        fig_rsharpe.add_hline(y=0, line_dash="dot", line_color="rgba(230,228,219,0.2)", line_width=1)
        _chart_layout(fig_rsharpe, "", height=380, y_title="Sharpe Ratio")
        fig_rsharpe.update_layout(hovermode="x unified")
        st.plotly_chart(fig_rsharpe, width='stretch', key="desemp_rsharpe")

        # ── Rolling Tracking Error ──
        st.markdown(f'<div class="tag-section-title">Rolling Tracking Error vs IBOV ({janela_du}du)</div>', unsafe_allow_html=True)
        st.markdown(_legenda(
            "<b>Tracking Error</b> = volatilidade do retorno ativo (fundo - IBOV). "
            "Quanto menor, mais o fundo acompanha o índice. TE alto = gestao ativa ou desvio significativo."), unsafe_allow_html=True)
        fig_rte = go.Figure()
        color_counter_te = [0]
        for name in selected_funds:
            if name == "IBOVESPA" or name not in fund_daily_rets:
                continue
            fund_dr = fund_daily_rets[name].dropna()
            active_ret = fund_dr.subtract(ibov_dr, fill_value=0).dropna()
            if len(active_ret) < janela_du + 5:
                continue
            roll_te = (active_ret.rolling(janela_du).std() * np.sqrt(252) * 100).dropna()
            is_synta = name in synta_names
            is_direct = name in direct_holdings_in_chart
            if is_synta:
                ls = dict(width=2.5, color=TAG_VERMELHO_LIGHT if "FIA II" in name else TAG_LARANJA, dash="solid")
            elif is_direct:
                ls = dict(width=1.8, color="#00CED1", dash="dot")
            else:
                ls = dict(width=2, color=TAG_CHART_COLORS[color_counter_te[0] % len(TAG_CHART_COLORS)], dash="solid")
                color_counter_te[0] += 1
            fig_rte.add_trace(go.Scatter(
                x=roll_te.index, y=roll_te.values, mode="lines",
                name=name, line=ls,
                hovertemplate=f"<b>{name}</b><br>%{{x|%d/%m/%Y}}<br>TE: %{{y:.1f}}% a.a.<extra></extra>",
            ))
        _chart_layout(fig_rte, "", height=380, y_title="Tracking Error (% a.a.)", y_suffix="%")
        fig_rte.update_layout(hovermode="x unified")
        st.plotly_chart(fig_rte, width='stretch', key="desemp_rte")

    # ----- SECTION 4: Metricas Avancadas -----
    st.markdown("---")
    st.markdown('<div class="tag-section-title">Métricas Avancadas de Risco</div>', unsafe_allow_html=True)
    st.markdown(_legenda(
        "<b>Sortino</b> = Sharpe ajustado (so penaliza downside). "
        "<b>VaR 95%</b> = perda maxima esperada em 95% dos dias. "
        "<b>Ulcer Index</b> = risco por profundidade/duracao de drawdowns (menor = melhor). "
        "<b>Capture Up/Down</b> = quanto o fundo captura das altas/baixas do IBOV. "
        "<b>Hit Rate</b> = % de meses em que o fundo bateu o IBOV."), unsafe_allow_html=True)

    adv_rows = []
    if "IBOVESPA" in fund_daily_rets:
        ibov_dr = fund_daily_rets["IBOVESPA"].dropna()
        # Monthly returns for capture ratio
        ibov_monthly = ibov_dr.resample("ME").apply(lambda x: (1 + x).prod() - 1)

        for name in selected_funds:
            if name not in fund_daily_rets:
                continue
            dr = fund_daily_rets[name].dropna()
            if len(dr) < 20:
                continue

            # Sortino
            excess = dr
            downside = excess[excess < 0]
            downside_dev = np.sqrt((downside ** 2).mean()) * np.sqrt(252) if len(downside) > 0 else 0
            n_d = len(dr)
            ret_total = fund_returns[name].iloc[-1] if name in fund_returns and len(fund_returns[name]) > 0 else 0
            ret_annual = ((1 + ret_total / 100) ** (252 / max(n_d, 1)) - 1) * 100
            sortino = ret_annual / (downside_dev * 100) if downside_dev > 0 else 0

            # VaR 95% and CVaR
            var_95 = np.nanpercentile(dr, 5) * 100
            cvar_95_vals = dr[dr <= np.nanpercentile(dr, 5)]
            cvar_95 = cvar_95_vals.mean() * 100 if len(cvar_95_vals) > 0 else var_95

            # Ulcer Index
            s_cum = fund_returns[name]
            cum_max = s_cum.cummax()
            dd_pct = s_cum - cum_max
            ulcer_idx = np.sqrt((dd_pct ** 2).mean())

            # Capture ratios (monthly)
            fund_monthly = dr.resample("ME").apply(lambda x: (1 + x).prod() - 1)
            common_m = fund_monthly.dropna().index.intersection(ibov_monthly.dropna().index)
            up_cap = down_cap = np.nan
            hit_rate = np.nan
            if len(common_m) >= 1 and name != "IBOVESPA":
                bm = ibov_monthly.loc[common_m]
                fm = fund_monthly.loc[common_m]
                up_mask = bm > 0
                down_mask = bm < 0
                if up_mask.sum() >= 1:
                    up_cap = fm[up_mask].mean() / bm[up_mask].mean() * 100
                if down_mask.sum() >= 1:
                    down_cap = fm[down_mask].mean() / bm[down_mask].mean() * 100
                hit_rate = (fm > bm).sum() / len(common_m) * 100

            adv_rows.append({
                "Fundo": name,
                "Sortino": sortino,
                "VaR 95% (%)": var_95,
                "CVaR 95% (%)": cvar_95,
                "Ulcer Index": ulcer_idx,
                "Capture Up (%)": up_cap,
                "Capture Down (%)": down_cap,
                "Hit Rate (%)": hit_rate,
            })

    if adv_rows:
        df_adv = pd.DataFrame(adv_rows).sort_values("Sortino", ascending=False)
        # Format numeric columns — fill NaN with "—" string for display
        disp = df_adv.copy()
        for col in ["Sortino"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        for col in ["VaR 95% (%)", "CVaR 95% (%)"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        for col in ["Ulcer Index"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
        for col in ["Capture Up (%)", "Capture Down (%)", "Hit Rate (%)"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
        st.dataframe(disp, hide_index=True,
                      height=min(len(disp) * 38 + 45, 500))

        # ── Capture Ratio Scatter ──
        df_cap = df_adv[df_adv["Capture Up (%)"].notna() & df_adv["Capture Down (%)"].notna()].copy()
        if not df_cap.empty and len(df_cap) >= 2:
            st.markdown('<div class="tag-section-title">Capture Ratio: Up vs Down</div>', unsafe_allow_html=True)
            st.markdown(_legenda(
                "<b>Ideal:</b> canto superior esquerdo = captura muito das altas e pouco das baixas. "
                "A diagonal tracejada indica captura simetrica. Fundos acima da diagonal sao assimetricos a favor do investidor."),
                unsafe_allow_html=True)
            fig_cap = go.Figure()
            color_idx_cap = 0
            for _, row in df_cap.iterrows():
                is_synta = row["Fundo"] in synta_names
                is_direct = row["Fundo"] in direct_holdings_in_chart
                if is_synta:
                    color = TAG_VERMELHO_LIGHT if "FIA II" in row["Fundo"] else TAG_LARANJA; symbol = "diamond"; sz = 14
                elif is_direct:
                    color = "#00CED1"; symbol = "square"; sz = 10
                else:
                    color = TAG_CHART_COLORS[color_idx_cap % len(TAG_CHART_COLORS)]; symbol = "circle"; sz = 12
                    color_idx_cap += 1
                fig_cap.add_trace(go.Scatter(
                    x=[row["Capture Down (%)"]], y=[row["Capture Up (%)"]],
                    mode="markers+text", text=[row["Fundo"]],
                    textposition="top center", textfont=dict(size=9, color=TAG_OFFWHITE),
                    marker=dict(size=sz, color=color, symbol=symbol, line=dict(width=1, color=TAG_OFFWHITE)),
                    showlegend=False,
                    hovertemplate=f"<b>{row['Fundo']}</b><br>Up: {row['Capture Up (%)']:.0f}%<br>Down: {row['Capture Down (%)']:.0f}%<extra></extra>",
                ))
            # Diagonal reference
            max_val = max(df_cap["Capture Up (%)"].max(), df_cap["Capture Down (%)"].max(), 120)
            fig_cap.add_trace(go.Scatter(
                x=[0, max_val], y=[0, max_val], mode="lines",
                line=dict(dash="dash", color="rgba(230,228,219,0.2)", width=1),
                showlegend=False, hoverinfo="skip",
            ))
            _chart_layout(fig_cap, "", height=420, y_title="Capture Up (%)", y_suffix="%")
            fig_cap.update_layout(xaxis_title="Capture Down (%)")
            st.plotly_chart(fig_cap, width='stretch', key="desemp_cap")


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    # Dynamic page title per tab
    _page_titles = {
        "📊 Atribuição IBOV": "Atribuição de Performance — IBOV",
        "📈 Synta FIA / FIA II": "Atribuição por Componente — Synta",
        "🔬 Brinson-Fachler": "Análise Brinson-Fachler",
        "⚖️ Comparativo Fundos vs IBOV": "Comparativo de Fundos",
        "🔍 Carteira Explodida por Ativo": "Carteira Explodida — Look-Through",
        "📉 Desempenho Individual": "Desempenho Individual — Fundos e Ativos",
    }
    st.markdown(f"# {_page_titles.get(page_sel, 'Monitoramento de Carteira')}")
    if page_sel == "📊 Atribuição IBOV":
        render_tab_ibov()
    elif page_sel == "📈 Synta FIA / FIA II":
        render_tab_synta()
    elif page_sel == "🔬 Brinson-Fachler":
        render_tab_brinson()
    elif page_sel == "⚖️ Comparativo Fundos vs IBOV":
        render_tab_comparativo()
    elif page_sel == "🔍 Carteira Explodida por Ativo":
        render_tab_carteira_explodida()
    elif page_sel == "📉 Desempenho Individual":
        render_tab_desempenho_individual()

if __name__ == "__main__":
    main()
