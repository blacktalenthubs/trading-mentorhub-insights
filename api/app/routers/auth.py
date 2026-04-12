"""Auth endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from jose import JWTError, jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, get_user_tier, is_trial_active, trial_days_remaining
from app.models.user import Subscription, User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRefreshResponse,
    UserResponse,
)

router = APIRouter()
settings = get_settings()

REFRESH_COOKIE = "refresh_token"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_access_token(user: User, tier: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "tier": tier,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _set_refresh_cookie(response: Response, token: str) -> None:
    # secure=False on localhost so the cookie is stored over plain HTTP
    is_dev = settings.DEBUG or settings.CORS_ORIGINS[0].startswith("http://localhost")
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=not is_dev,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth" if not is_dev else "/",
    )


def _build_user_response(user: User, tier: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        tier=tier,
        trial_active=is_trial_active(user),
        trial_days_left=trial_days_remaining(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    user = User(
        email=body.email.lower(),
        password_hash=_hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    db.add(user)
    await db.flush()

    # Create free subscription with 3-day Pro trial
    from app.tier import TRIAL_DURATION_DAYS
    # Use naive UTC datetime — Postgres column is TIMESTAMP WITHOUT TIME ZONE
    trial_ends = datetime.utcnow() + timedelta(days=TRIAL_DURATION_DAYS)
    sub = Subscription(user_id=user.id, tier="free", trial_ends_at=trial_ends)
    db.add(sub)
    await db.flush()
    # Attach subscription to user object so _build_user_response can read it
    user.subscription = sub

    # During trial, effective tier is "pro"
    tier = "pro"
    access_token = _create_access_token(user, tier)
    refresh_token = _create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return AuthResponse(
        access_token=access_token,
        user=_build_user_response(user, tier),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).options(selectinload(User.subscription)).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    tier = get_user_tier(user)

    access_token = _create_access_token(user, tier)
    refresh_token = _create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return AuthResponse(
        access_token=access_token,
        user=_build_user_response(user, tier),
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload["sub"])
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).options(selectinload(User.subscription)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    tier = get_user_tier(user)

    # Rotate refresh token
    new_access = _create_access_token(user, tier)
    new_refresh = _create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)

    return TokenRefreshResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    is_dev = settings.DEBUG or settings.CORS_ORIGINS[0].startswith("http://localhost")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth" if not is_dev else "/")
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    tier = get_user_tier(user)
    return _build_user_response(user, tier)


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset link. Always returns 200 to avoid leaking user existence."""
    import logging

    logger = logging.getLogger(__name__)

    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if user:
        from app.models.password_reset import PasswordResetToken

        token = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            token=token,
            user_id=user.id,
            expires_at=expires_at,
        )
        db.add(reset_token)
        await db.flush()

        # Send reset email (fire-and-forget, don't block response)
        reset_link = f"https://www.tradingwithai.ai/reset-password?token={token}"
        try:
            from alerting.notifier import send_plain_email

            send_plain_email(
                user.email,
                "TradeCoPilot — Reset Your Password",
                f"Hi {user.display_name or 'there'},\n\n"
                f"Click the link below to reset your password. "
                f"This link expires in 1 hour.\n\n"
                f"{reset_link}\n\n"
                f"If you didn't request this, you can safely ignore this email.\n\n"
                f"— TradeCoPilot",
            )
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid token."""
    from app.models.password_reset import PasswordResetToken

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == body.token)
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if reset_token.used:
        raise HTTPException(status_code=400, detail="This reset link has already been used")

    now = datetime.now(timezone.utc)
    # Handle both timezone-aware and naive datetimes from DB
    expires = reset_token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    # Update the user's password
    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = _hash_password(body.new_password)
    reset_token.used = 1
    await db.flush()

    return {"message": "Password has been reset successfully. You can now sign in."}


@router.get("/usage")
async def usage_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return today's usage counts and limits for the current user."""
    from app.tier import get_limits

    tier = get_user_tier(user)
    limits = get_limits(tier)
    today = date.today().isoformat()

    result = await db.execute(
        text(
            "SELECT feature, usage_count FROM usage_limits "
            "WHERE user_id = :uid AND usage_date = :d"
        ),
        {"uid": user.id, "d": today},
    )
    usage_rows = {row[0]: row[1] for row in result.fetchall()}

    # AI scan delivered count (in-memory counter from scanner worker)
    try:
        from analytics.ai_day_scanner import get_user_ai_scan_count
        ai_scan_count = get_user_ai_scan_count(user.id, today)
    except Exception:
        ai_scan_count = 0

    ai_scan_max = limits.get("ai_scan_alerts_per_day")
    ai_scan_limit_reached = bool(
        ai_scan_max is not None and ai_scan_count >= ai_scan_max
    )

    return {
        "tier": tier,
        "trial_active": is_trial_active(user),
        "trial_days_left": trial_days_remaining(user),
        "limits": limits,
        "usage_today": usage_rows,
        "ai_scan_alerts_today": ai_scan_count,
        "ai_scan_alerts_max": ai_scan_max,
        "ai_scan_limit_reached": ai_scan_limit_reached,
    }
