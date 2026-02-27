"""
SSO Authentication Guard for TAG Gestao ecosystem.
Validates JWT tokens issued by the TAG Gestao Portal.
Drop this file into the root of any Streamlit app to enable SSO.
"""
import streamlit as st
import jwt  # PyJWT
import os
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────
def _get_sso_secret():
    secret = os.environ.get("SSO_SECRET", "")
    if secret:
        return secret
    try:
        return st.secrets["SSO_SECRET"]
    except Exception:
        return ""

SSO_SECRET = _get_sso_secret()
SSO_ALGORITHM = "HS256"
PORTAL_URL = "https://tag-gestao.streamlit.app"

# ── TAG Brand colors (minimal subset for access denied page) ──
_TAG_VERMELHO = "#630D24"
_TAG_OFFWHITE = "#E6E4DB"
_TAG_LARANJA = "#FF8853"
_TAG_BG_DARK = "#1A0A10"
_TAG_BG_CARD = "#2A1520"
_TAG_TEXT_MUTED = "#9A9590"


def validate_sso_token() -> dict | None:
    """
    Check st.query_params for 'sso_token', decode and validate it.
    Returns the payload dict on success, None on failure.
    """
    token = st.query_params.get("sso_token")
    if not token:
        return None
    if not SSO_SECRET:
        return None
    try:
        payload = jwt.decode(token, SSO_SECRET, algorithms=[SSO_ALGORITHM])
        required = {"user_id", "email", "nome", "role", "exp"}
        if not required.issubset(payload.keys()):
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def render_access_denied():
    """Render a branded 'Acesso Negado' page and stop execution."""
    st.markdown(f"""
    <style>
        [data-testid="stSidebar"] {{ display: none; }}
        [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
        .sso-denied-wrapper {{
            max-width: 480px;
            margin: 80px auto;
            text-align: center;
            padding: 48px 36px;
            background: linear-gradient(135deg, {_TAG_BG_CARD} 0%, #321A28 100%);
            border: 1px solid {_TAG_VERMELHO}30;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(99,13,36,0.25);
        }}
        .sso-denied-icon {{ font-size: 4rem; margin-bottom: 16px; }}
        .sso-denied-title {{
            color: {_TAG_OFFWHITE}; font-size: 1.5rem;
            font-weight: 600; margin-bottom: 8px;
        }}
        .sso-denied-msg {{
            color: {_TAG_TEXT_MUTED}; font-size: 0.9rem;
            line-height: 1.5; margin-bottom: 24px;
        }}
        .sso-denied-wrapper a {{
            color: {_TAG_LARANJA} !important;
            text-decoration: none;
            font-weight: 600;
        }}
    </style>
    <div class="sso-denied-wrapper">
        <div class="sso-denied-icon">🔒</div>
        <div class="sso-denied-title">Acesso Negado</div>
        <div class="sso-denied-msg">
            Este relatorio requer autenticacao via Portal TAG Gestao.<br>
            Faca login no portal e acesse o relatorio pelo card correspondente.
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.link_button(
            "Ir para o Portal TAG Gestao",
            PORTAL_URL,
            use_container_width=True,
        )

    st.stop()


def require_sso() -> dict:
    """
    Main guard function. Call at the top of your app.
    Returns the user dict if authenticated, otherwise renders
    access denied and stops.

    The returned dict contains: user_id, email, nome, role
    """
    # If already authenticated in this session, skip re-validation
    if "sso_user" in st.session_state:
        return st.session_state["sso_user"]

    payload = validate_sso_token()
    if payload is None:
        render_access_denied()
        return {}  # unreachable (st.stop called above), but for type safety

    user_data = {
        "user_id": payload["user_id"],
        "email": payload["email"],
        "nome": payload["nome"],
        "role": payload["role"],
    }
    st.session_state["sso_user"] = user_data

    # Clean the token from the URL bar (prevents sharing URL with valid token)
    st.query_params.clear()

    return user_data
