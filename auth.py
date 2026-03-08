"""Authentication module — email/password auth with persistent session management.

Sessions persist across browser restarts via a cookie (``ts_session``).
The cookie is set/cleared with a small JS snippet injected via
``st.components.v1.html``.  No third-party cookie library required.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta

import bcrypt
import streamlit as st
import streamlit.components.v1 as components

from db import IntegrityError, get_db

logger = logging.getLogger(__name__)

SESSION_EXPIRY_DAYS = 30
_COOKIE_NAME = "ts_session"
_RESET_TOKEN_EXPIRY_HOURS = 1
_MAX_RESET_TOKENS_PER_USER = 3
_APP_URL = os.environ.get("APP_URL", "https://tradecopilot.streamlit.app")


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

def create_user(email: str, password: str, display_name: str | None = None) -> int:
    """Register a new user. Returns user_id. Raises ValueError if email exists."""
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("Email and password are required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    pw_hash = hash_password(password)
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
                (email, pw_hash, display_name or email.split("@")[0]),
            )
            return cur.lastrowid
    except IntegrityError:
        raise ValueError("An account with this email already exists.")


def authenticate_user(email: str, password: str) -> dict | None:
    """Validate credentials. Returns user dict or None."""
    email = email.strip().lower()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, display_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if row and verify_password(password, row["password_hash"]):
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def request_password_reset(email: str) -> bool:
    """Generate a reset token and email it. Always returns True (no enumeration)."""
    email = email.strip().lower()
    if not email:
        return True

    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()

    if not row:
        return True  # Same response — no email enumeration

    user_id = row["id"]
    token = uuid.uuid4().hex
    expires = datetime.utcnow() + timedelta(hours=_RESET_TOKEN_EXPIRY_HOURS)

    with get_db() as conn:
        # Enforce max tokens per user — delete oldest unused beyond limit
        conn.execute(
            """DELETE FROM password_reset_tokens
               WHERE user_id = ? AND used = 0
               AND token NOT IN (
                   SELECT token FROM password_reset_tokens
                   WHERE user_id = ? AND used = 0
                   ORDER BY created_at DESC LIMIT ?
               )""",
            (user_id, user_id, _MAX_RESET_TOKENS_PER_USER - 1),
        )
        conn.execute(
            """INSERT INTO password_reset_tokens (token, user_id, expires_at)
               VALUES (?, ?, ?)""",
            (token, user_id, expires.isoformat()),
        )

    # Send reset email
    reset_link = f"{_APP_URL}?reset_token={token}"
    subject = "TradeCoPilot \u2014 Password Reset"
    body = (
        f"You requested a password reset for your TradeCoPilot account.\n\n"
        f"Click the link below to set a new password:\n{reset_link}\n\n"
        f"This link expires in {_RESET_TOKEN_EXPIRY_HOURS} hour.\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    try:
        from alerting.notifier import send_plain_email
        send_plain_email(email, subject, body)
    except Exception:
        logger.exception("Failed to send reset email to %s", email)

    return True


def validate_reset_token(token: str) -> dict | None:
    """Check if a reset token is valid. Returns user dict or None."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.display_name
               FROM password_reset_tokens t JOIN users u ON t.user_id = u.id
               WHERE t.token = ? AND t.used = 0 AND t.expires_at > ?""",
            (token, datetime.utcnow().isoformat()),
        ).fetchone()
    if row:
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
    return None


def reset_password(token: str, new_password: str) -> bool:
    """Reset a user's password using a valid token. Returns True on success."""
    if len(new_password) < 6:
        return False

    user = validate_reset_token(token)
    if not user:
        return False

    pw_hash = hash_password(new_password)
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, user["id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE token = ?",
            (token,),
        )
    return True


def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    """Change password for a logged-in user. Returns (success, message)."""
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters."

    with get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    if not row:
        return False, "User not found."

    if not verify_password(current_password, row["password_hash"]):
        return False, "Current password is incorrect."

    pw_hash = hash_password(new_password)
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, user_id),
        )
    return True, "Password changed successfully."


# ---------------------------------------------------------------------------
# Persistent session tokens
# ---------------------------------------------------------------------------

def _create_session_token(user_id: int) -> str:
    """Create a persistent session token stored in the DB."""
    token = uuid.uuid4().hex
    expires = datetime.utcnow() + timedelta(days=SESSION_EXPIRY_DAYS)
    with get_db() as conn:
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
    with get_db() as conn:
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
    with get_db() as conn:
        conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))


# ---------------------------------------------------------------------------
# Cookie helpers (zero-dependency, JS-based)
# ---------------------------------------------------------------------------

def _set_cookie(token: str):
    """Set a persistent browser cookie via injected JS.

    Uses ``window.parent.document.cookie`` so the cookie is set on the
    Streamlit app's domain rather than inside the components iframe.
    """
    max_age = SESSION_EXPIRY_DAYS * 86400
    components.html(
        f"""<script>
        try {{ window.parent.document.cookie = "{_COOKIE_NAME}={token}; path=/; max-age={max_age}; SameSite=Lax"; }}
        catch(e) {{ document.cookie = "{_COOKIE_NAME}={token}; path=/; max-age={max_age}; SameSite=Lax"; }}
        </script>""",
        height=0,
    )


def _clear_cookie():
    """Delete the session cookie via injected JS."""
    components.html(
        f"""<script>
        try {{ window.parent.document.cookie = "{_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax"; }}
        catch(e) {{ document.cookie = "{_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax"; }}
        </script>""",
        height=0,
    )


def _read_cookie() -> str | None:
    """Read the session cookie from the request headers.

    Streamlit exposes cookies via ``st.context.cookies`` (>=1.37) or via
    the internal header accessor.  Returns the token string or None.
    """
    try:
        # st.context.cookies available since Streamlit ~1.37
        cookies = st.context.cookies
        return cookies.get(_COOKIE_NAME) or None
    except Exception:
        pass

    try:
        # Fallback: parse the Cookie header from the HTTP request
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
    """Check for logged-in user: session_state → cookie → query param.

    Tries both token sources independently so a stale cookie doesn't
    block a valid query-param token.
    """
    # Fast path: already in memory
    user = st.session_state.get("user")
    if user:
        return user

    # Collect both token sources
    cookie_token = None
    try:
        cookie_token = _read_cookie()
    except Exception:
        pass

    qp_token = st.query_params.get("session")

    # Try each token — cookie first, then query param
    for token in [cookie_token, qp_token]:
        if not token:
            continue
        user = _get_user_by_token(token)
        if user:
            st.session_state["user"] = user
            # Ensure query param is always present as reliable fallback
            if st.query_params.get("session") != token:
                st.query_params["session"] = token
            return user

    # Both tokens invalid — clean up
    if cookie_token:
        st.session_state["_clear_session"] = True
    if qp_token:
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
    # Deferred cookie cleanup (scheduled by get_current_user on invalid token)
    if st.session_state.pop("_clear_session", False):
        _clear_cookie()

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
            from db import upsert_subscription
            user_id = create_user(email, password, display_name or None)
            upsert_subscription(user_id, "free")
            user = get_user_by_id(user_id)
            login_user(user)
            st.success("Account created!")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _render_forgot_password_form():
    """Forgot password form inside a tab."""
    with st.form("forgot_password_form"):
        email = st.text_input("Email", key="forgot_email")
        submitted = st.form_submit_button("Send Reset Link", use_container_width=True)

    if submitted:
        if not email:
            st.error("Please enter your email address.")
            return
        request_password_reset(email)
        st.success(
            "If an account with that email exists, a reset link has been sent. "
            "Check your inbox (and spam folder)."
        )


def _render_reset_password_form(token: str):
    """Password reset form shown when arriving via reset link."""
    user = validate_reset_token(token)
    if not user:
        st.title("Invalid or Expired Link")
        st.error(
            "This password reset link is invalid or has expired. "
            "Please request a new one."
        )
        if st.button("Back to Login"):
            st.query_params.clear()
            st.rerun()
        return

    st.title("Reset Your Password")
    st.caption(f"Resetting password for **{user['email']}**")

    with st.form("reset_password_form"):
        new_pw = st.text_input("New Password", type="password", key="reset_pw")
        confirm = st.text_input("Confirm Password", type="password", key="reset_confirm")
        submitted = st.form_submit_button("Reset Password", use_container_width=True)

    if submitted:
        if not new_pw or not confirm:
            st.error("Please fill in both fields.")
            return
        if new_pw != confirm:
            st.error("Passwords do not match.")
            return
        if len(new_pw) < 6:
            st.error("Password must be at least 6 characters.")
            return

        if reset_password(token, new_pw):
            st.success("Password reset! You can now log in with your new password.")
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Reset failed. The link may have expired. Please request a new one.")


# ---------------------------------------------------------------------------
# Page protection
# ---------------------------------------------------------------------------

def require_auth() -> dict:
    """Call at the top of any protected page.

    If logged in: returns user dict, renders sidebar info.
    If not logged in: renders login/register form, then st.stop().
    Handles reset_token query param for password reset flow.
    """
    user = get_current_user()
    if user:
        # Sidebar user info + logout is rendered by ui_theme._render_sidebar_user()
        # which is called by setup_page() after require_auth() returns.
        return user

    # Check for password reset token in query params
    reset_token = st.query_params.get("reset_token")
    if reset_token:
        _render_reset_password_form(reset_token)
        st.stop()

    st.title("Login Required")
    st.caption("Sign in to TradeCoPilot")

    tab_login, tab_register, tab_forgot = st.tabs(
        ["Login", "Register", "Forgot Password"]
    )
    with tab_login:
        _render_login_form()
    with tab_register:
        _render_register_form()
    with tab_forgot:
        _render_forgot_password_form()

    st.stop()
