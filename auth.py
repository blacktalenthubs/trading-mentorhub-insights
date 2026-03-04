"""Authentication module — email/password auth with persistent session management.

Sessions persist across browser restarts via a cookie (``ts_session``).
The cookie is set/cleared with a small JS snippet injected via
``st.components.v1.html``.  No third-party cookie library required.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta

import bcrypt
import streamlit as st
import streamlit.components.v1 as components

from config import DB_PATH

SESSION_EXPIRY_DAYS = 30
_COOKIE_NAME = "ts_session"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_user(email: str, password: str, display_name: str | None = None) -> int:
    """Register a new user. Returns user_id. Raises ValueError if email exists."""
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("Email and password are required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    pw_hash = hash_password(password)
    try:
        with _get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
                (email, pw_hash, display_name or email.split("@")[0]),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists.")


def authenticate_user(email: str, password: str) -> dict | None:
    """Validate credentials. Returns user dict or None."""
    email = email.strip().lower()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, display_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if row and verify_password(password, row["password_hash"]):
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


def get_user_by_id(user_id: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


# ---------------------------------------------------------------------------
# Persistent session tokens
# ---------------------------------------------------------------------------

def _create_session_token(user_id: int) -> str:
    """Create a persistent session token stored in the DB."""
    token = uuid.uuid4().hex
    expires = datetime.utcnow() + timedelta(days=SESSION_EXPIRY_DAYS)
    with _get_conn() as conn:
        # Clean expired tokens
        conn.execute(
            "DELETE FROM session_tokens WHERE expires_at < ?",
            (datetime.utcnow().isoformat(),),
        )
        conn.execute(
            "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat()),
        )
    return token


def _get_user_by_token(token: str) -> dict | None:
    """Look up a session token and return the associated user."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name
               FROM session_tokens t JOIN users u ON t.user_id = u.id
               WHERE t.token = ? AND t.expires_at > ?""",
            (token, datetime.utcnow().isoformat()),
        ).fetchone()
    if row:
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


def _delete_session_token(token: str):
    with _get_conn() as conn:
        conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))


# ---------------------------------------------------------------------------
# Cookie helpers (zero-dependency, JS-based)
# ---------------------------------------------------------------------------

def _set_cookie(token: str):
    """Set a persistent browser cookie via injected JS."""
    max_age = SESSION_EXPIRY_DAYS * 86400
    components.html(
        f"""<script>
        document.cookie = "{_COOKIE_NAME}={token}; path=/; max-age={max_age}; SameSite=Lax";
        </script>""",
        height=0,
    )


def _clear_cookie():
    """Delete the session cookie via injected JS."""
    components.html(
        f"""<script>
        document.cookie = "{_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax";
        </script>""",
        height=0,
    )


def _read_cookie() -> str | None:
    """Read the session cookie from the request headers.

    Streamlit exposes cookies via ``st.context.cookies`` (>=1.37) or via
    the internal header accessor.  Returns the token string or None.
    """
    # st.context.cookies available since Streamlit ~1.37
    try:
        cookies = st.context.cookies
        return cookies.get(_COOKIE_NAME) or None
    except AttributeError:
        pass

    # Fallback: parse the Cookie header from the HTTP request
    try:
        headers = st.context.headers
        cookie_header = headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{_COOKIE_NAME}="):
                return part.split("=", 1)[1] or None
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Session management (persistent across page refreshes & browser restarts)
# ---------------------------------------------------------------------------

def get_current_user() -> dict | None:
    """Check for logged-in user: session_state → cookie → query param."""
    # Fast path: already in memory
    user = st.session_state.get("user")
    if user:
        return user

    # Try persistent cookie first (survives browser restarts)
    token = _read_cookie()

    # Fallback: legacy query-param token
    if not token:
        token = st.query_params.get("session")

    if token:
        user = _get_user_by_token(token)
        if user:
            st.session_state["user"] = user
            return user
        else:
            # Token expired or invalid — clean up
            _clear_cookie()
            if "session" in st.query_params:
                del st.query_params["session"]
    return None


def login_user(user: dict):
    """Log in: save to session_state + set persistent cookie + query param."""
    st.session_state["user"] = user
    token = _create_session_token(user["id"])
    _set_cookie(token)
    st.query_params["session"] = token  # keep as fallback
    st.session_state.pop("watchlist", None)  # Re-fetch for this user


def logout_user():
    """Log out: clear session_state + delete cookie + query param."""
    token = _read_cookie() or st.query_params.get("session")
    if token:
        _delete_session_token(token)
    _clear_cookie()
    if "session" in st.query_params:
        del st.query_params["session"]
    st.session_state.pop("user", None)


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------

def render_sidebar_user_info():
    """Show logged-in user info + logout button in sidebar (compact)."""
    user = get_current_user()
    if not user:
        return
    with st.sidebar:
        _info_col, _logout_col = st.columns([3, 1])
        _info_col.markdown(
            f"**{user['display_name']}**"
            f"<br><span style='color:#888;font-size:0.75rem'>{user['email']}</span>",
            unsafe_allow_html=True,
        )
        if _logout_col.button("Logout", key="sidebar_logout"):
            logout_user()
            st.rerun()


def _render_login_form():
    """Login form inside a tab."""
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
            return
        user = authenticate_user(email, password)
        if user:
            login_user(user)
            st.rerun()
        else:
            st.error("Invalid email or password.")


def _render_register_form():
    """Registration form inside a tab."""
    with st.form("register_form"):
        email = st.text_input("Email", key="reg_email")
        display_name = st.text_input("Display Name (optional)", key="reg_name")
        password = st.text_input("Password", type="password", key="reg_pass")
        confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
        submitted = st.form_submit_button("Create Account", use_container_width=True)

    if submitted:
        if password != confirm:
            st.error("Passwords do not match.")
            return
        try:
            user_id = create_user(email, password, display_name or None)
            user = get_user_by_id(user_id)
            login_user(user)
            st.success("Account created!")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


# ---------------------------------------------------------------------------
# Page protection
# ---------------------------------------------------------------------------

def require_auth() -> dict:
    """Call at the top of any protected page.

    If logged in: returns user dict, renders sidebar info.
    If not logged in: renders login/register form, then st.stop().
    """
    user = get_current_user()
    if user:
        render_sidebar_user_info()
        return user

    st.title("Login Required")
    st.caption("Sign in to TradeSignal")

    tab_login, tab_register = st.tabs(["Login", "Register"])
    with tab_login:
        _render_login_form()
    with tab_register:
        _render_register_form()

    st.stop()
