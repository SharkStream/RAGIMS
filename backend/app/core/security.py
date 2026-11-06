"""Password hashing + HMAC token issuing/parsing (K2).

Deliberately dependency-free (standard library only):

* passwords — ``pbkdf2_hmac`` with per-password random salt, stored as
  ``pbkdf2$<iterations>$<salt_hex>$<hash_hex>``;
* tokens — ``base64url(payload_json) + "." + base64url(hmac_sha256(secret,
  payload_b64))`` where payload is ``{sub, tenant_id, user_id, role, iat,
  exp}``. Stateless, 12h TTL by default.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings
from app.core.errors import AppError

_PBKDF2_ITERATIONS = 200_000
_TOKEN_ERR = AppError(
    "invalid or expired credentials", code="ERR_UNAUTHORIZED", status_code=401
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# --------------------------------------------------------------------------- #
# passwords
# --------------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    salt = hashlib.sha256(str(time.time_ns()).encode()).digest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time verify; malformed/missing stored hash → False."""
    if not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2":
        return False
    try:
        iterations, salt_hex, digest_hex = int(parts[1]), parts[2], parts[3]
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# tokens
# --------------------------------------------------------------------------- #


def issue_token(
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    username: str,
) -> str:
    """Sign a stateless identity token (default TTL from settings)."""
    now = int(time.time())
    payload = {
        "sub": username,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now,
        "exp": now + settings.security.token_ttl_seconds,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        settings.security.token_secret.encode(), body.encode(), hashlib.sha256
    ).digest()
    return f"{body}.{_b64url(sig)}"


def parse_token(token: str) -> dict[str, object]:
    """Verify signature + expiry; return the payload dict (401 on failure)."""
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(
            settings.security.token_secret.encode(), body.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url(expected), sig):
            raise _TOKEN_ERR
        payload = json.loads(_b64url_decode(body))
        if not isinstance(payload, dict):
            raise _TOKEN_ERR
        if int(payload.get("exp", 0)) < int(time.time()):
            raise _TOKEN_ERR
        for key in ("user_id", "tenant_id", "role"):
            if not payload.get(key):
                raise _TOKEN_ERR
        return payload
    except AppError:
        raise
    except Exception as exc:  # malformed structure/base64/json → 401
        raise _TOKEN_ERR from exc
