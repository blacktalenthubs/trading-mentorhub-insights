"""Authentication module — email/password auth with persistent session management."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta

import bcrypt
import streamlit as st

from config import DB_PATH

SESSION_EXPIRY_DAYS = 30


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
# Session management (persistent across page refreshes)
# ---------------------------------------------------------------------------

def get_current_user() -> dict | None:
    """Check for logged-in user: session_state first, then persistent token."""
    # Fast path: already in memory
    user = st.session_state.get("user")
    if user:
        return user

    # Check for persistent token in URL query params
    token = st.query_params.get("session")
    if token:
        user = _get_user_by_token(token)
        if user:
            st.session_state["user"] = user
            return user
        else:
            # Token expired or invalid — clean up
            del st.query_params["session"]
    return None


def login_user(user: dict):
    """Log in: save to session_state + create persistent token in query params."""
    st.session_state["user"] = user
    token = _create_session_token(user["id"])
    st.query_params["session"] = token


def logout_user():
    """Log out: clear session_state + delete persistent token."""
    token = st.query_params.get("session")
    if token:
        _delete_session_token(token)
        del st.query_params["session"]
    st.session_state.pop("user", None)


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------

def render_sidebar_user_info():
    """Show logged-in user info + logout button in sidebar."""
    user = get_current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown(f"**{user['display_name']}**")
        st.caption(user["email"])
        if st.button("Logout", key="sidebar_logout"):
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
    st.caption("Sign in to access your trade analytics.")

    tab_login, tab_register = st.tabs(["Login", "Register"])
    with tab_login:
        _render_login_form()
    with tab_register:
        _render_register_form()

    st.stop()
