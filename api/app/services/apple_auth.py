"""Sign in with Apple — ID-token verification.

Apple signs the JWT with one of a small rotating set of public keys
exposed at https://appleid.apple.com/auth/keys (JWKS). We fetch + cache
those keys, then verify the token's signature, issuer, audience, and
expiry. No private key from us is required for this flow — that's only
needed for server-to-server auth (refresh tokens, code exchange), which
we don't use.

Reference: https://developer.apple.com/documentation/sign_in_with_apple/verifying_a_user
"""

from __future__ import annotations

import time
from typing import Any, Dict

import httpx
from jose import jwt
from jose.utils import base64url_decode

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# Cache JWKS for 1 hour. Apple rotates rarely; even with rotation, a stale
# cache just means the next sign-in retries — no user-visible failure.
_CACHE_TTL_SEC = 3600
_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0}


async def _fetch_jwks() -> Dict[str, Any]:
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < _CACHE_TTL_SEC:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(APPLE_JWKS_URL)
        resp.raise_for_status()
        keys = resp.json()
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def _find_key(jwks: Dict[str, Any], kid: str) -> Dict[str, Any] | None:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def verify_apple_id_token(id_token: str, audience: str) -> Dict[str, Any]:
    """Return the verified claims dict, or raise ValueError on any failure."""
    if not audience:
        raise ValueError("Apple audience (Services ID) not configured")

    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as e:
        raise ValueError(f"Malformed Apple ID token header: {e}") from e

    kid = header.get("kid")
    if not kid:
        raise ValueError("Apple ID token missing 'kid' in header")

    jwks = await _fetch_jwks()
    key = _find_key(jwks, kid)
    if not key:
        # Maybe Apple rotated — refresh once and retry
        _jwks_cache["fetched_at"] = 0
        jwks = await _fetch_jwks()
        key = _find_key(jwks, kid)
    if not key:
        raise ValueError("Apple public key for token's 'kid' not found in JWKS")

    # python-jose accepts the JWK dict directly
    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=audience,
            issuer=APPLE_ISSUER,
            # clock skew tolerance — small to match Google flow
            options={"verify_aud": True, "verify_iss": True, "verify_exp": True},
        )
    except Exception as e:
        raise ValueError(f"Apple ID token verification failed: {e}") from e

    return claims


# Re-export for callers that need to detect base64url quirks (rare)
__all__ = ["verify_apple_id_token", "base64url_decode"]
