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

# ── TAG Brand colors ──
_TAG_VERMELHO = "#630D24"
_TAG_OFFWHITE = "#E6E4DB"
_TAG_LARANJA = "#FF8853"
_TAG_BG_DARK = "#1A0A10"
_TAG_BG_CARD = "#2A1520"
_TAG_BG_CARD_ALT = "#321A28"
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

    # ── CSS styles ──
    st.markdown(f"""
    <style>
        [data-testid="stSidebar"] {{ display: none !important; }}
        [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
        header[data-testid="stHeader"] {{ background: transparent; }}
        #MainMenu {{ visibility: hidden; }}
        [data-testid="stMainBlockContainer"] {{
            max-width: 460px;
            margin: 0 auto;
        }}
        [data-testid="stMainBlockContainer"] > div {{
            padding-top: 1rem;
        }}
        .sso-logo {{
            text-align: center;
            margin: 36px 0 24px 0;
        }}
        .sso-logo-main {{
            color: {_TAG_LARANJA};
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0.25em;
            margin: 0;
            line-height: 1;
        }}
        .sso-logo-sub {{
            color: {_TAG_TEXT_MUTED};
            font-size: 0.65rem;
            letter-spacing: 0.45em;
            text-transform: uppercase;
            margin-top: 2px;
        }}
        .sso-card {{
            max-width: 400px;
            margin: 0 auto;
            padding: 40px 36px 36px 36px;
            background: linear-gradient(135deg, {_TAG_BG_CARD} 0%, {_TAG_BG_CARD_ALT} 100%);
            border: 1px solid {_TAG_VERMELHO}30;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(99,13,36,0.25);
            text-align: center;
        }}
        .sso-icon {{
            margin-bottom: 20px;
            display: flex;
            justify-content: center;
        }}
        .sso-icon svg {{
            filter: drop-shadow(0 2px 8px rgba(255,136,83,0.2));
        }}
        .sso-title {{
            color: {_TAG_OFFWHITE};
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: 0.02em;
        }}
        .sso-divider {{
            width: 48px;
            height: 2px;
            background: linear-gradient(90deg, transparent, {_TAG_LARANJA}80, transparent);
            margin: 0 auto 16px auto;
            border-radius: 1px;
        }}
        .sso-msg {{
            color: {_TAG_TEXT_MUTED};
            font-size: 0.88rem;
            line-height: 1.65;
            margin-bottom: 8px;
        }}
        .sso-msg strong {{
            color: {_TAG_OFFWHITE};
            font-weight: 600;
        }}
        .sso-footer {{
            text-align: center;
            color: {_TAG_TEXT_MUTED};
            font-size: 0.7rem;
            margin-top: 28px;
            opacity: 0.5;
        }}
    </style>
    """, unsafe_allow_html=True)

    # ── Logo ──
    st.markdown(
        f'<div class="sso-logo">'
        f'<div class="sso-logo-main">TAG</div>'
        f'<div class="sso-logo-sub">G E S T \u00c3 O</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Card with icon, title, message ──
    st.markdown(
        f'<div class="sso-card">'
        f'<div class="sso-icon">'
        f'<svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="M12 2L4 5.5V11.5C4 16.45 7.4 21.05 12 22C16.6 21.05 20 16.45 20 11.5V5.5L12 2Z" '
        f'stroke="#FF8853" stroke-width="1.5" fill="rgba(255,136,83,0.08)"/>'
        f'<rect x="9.5" y="10" width="5" height="4.5" rx="0.8" '
        f'stroke="#FF8853" stroke-width="1.3" fill="none"/>'
        f'<path d="M10.5 10V8.5C10.5 7.67 11.17 7 12 7C12.83 7 13.5 7.67 13.5 8.5V10" '
        f'stroke="#FF8853" stroke-width="1.3" fill="none" stroke-linecap="round"/>'
        f'<circle cx="12" cy="12" r="0.6" fill="#FF8853"/>'
        f'</svg>'
        f'</div>'
        f'<div class="sso-title">Acesso Restrito</div>'
        f'<div class="sso-divider"></div>'
        f'<div class="sso-msg">'
        f'Este relat\u00f3rio requer autentica\u00e7\u00e3o via '
        f'<strong>Portal TAG Gest\u00e3o</strong>.<br>'
        f'Fa\u00e7a login no portal e acesse pelo card correspondente.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Button (Streamlit native — guaranteed to work) ──
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.link_button(
            "\U0001F512  Acessar Portal TAG Gest\u00e3o",
            PORTAL_URL,
            use_container_width=True,
        )

    # ── Footer ──
    st.markdown(
        f'<div class="sso-footer">TAG Investimentos \u00b7 Acesso Seguro</div>',
        unsafe_allow_html=True,
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
