"""
LYFTR AI - Authentication Service
JWT token creation/verification and password hashing.
"""
import os
import hashlib
import hmac
import base64
import uuid
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Simple JWT implementation without python-jose (stdlib only)
# Uses HS256 (HMAC-SHA256) for signing
# ---------------------------------------------------------------------------

import json
import struct


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _get_secret() -> bytes:
    secret = os.getenv("JWT_SECRET_KEY", "lyftr-ai-dev-secret-change-in-production")
    return secret.encode()


def create_access_token(data: dict, expires_minutes: int = 60 * 24) -> str:
    """Create a signed JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(data)
    exp = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload["exp"] = int(exp.timestamp())
    payload["iat"] = int(datetime.utcnow().timestamp())
    payload["jti"] = str(uuid.uuid4())

    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload or None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts
        signing_input = f"{h}.{p}".encode()
        expected_sig = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(p))
        # Check expiry
        exp = payload.get("exp", 0)
        if exp and datetime.utcnow().timestamp() > exp:
            return None
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Password hashing using PBKDF2-HMAC-SHA256 (stdlib, no bcrypt needed)
# ---------------------------------------------------------------------------

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}:{base64.b64encode(salt).decode()}:{base64.b64encode(dk).decode()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its PBKDF2 hash."""
    try:
        parts = hashed.split(":")
        if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        iterations = int(parts[2])
        salt = base64.b64decode(parts[3])
        stored_dk = base64.b64decode(parts[4])
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False
