"""Hosted OIDC ID-token verification. JWKS is injected; never taken from the token."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from harpy.identity.headers import authorization_bearer, request_headers
from harpy.identity.types import AuthenticationError

ALLOWED_ALGS = frozenset({"RS256", "ES256"})
CLOCK_SKEW = timedelta(seconds=60)
Jwks = dict[str, Any]
JwksLoader = Callable[[], Jwks]


def _b64url_decode(text: str) -> bytes:
    import base64

    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    audience: str


@dataclass(frozen=True)
class OidcClaims:
    issuer: str
    subject: str
    audience: str
    expires_at: datetime


class OidcAuthenticator:
    def __init__(
        self,
        config: OidcConfig,
        *,
        jwks: Jwks,
        jwks_loader: JwksLoader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self._jwks = jwks
        self._jwks_loader = jwks_loader
        self._clock = clock or (lambda: datetime.now(UTC))
        self._refreshed = False

    def authenticate(self, headers: Mapping[str, str]) -> OidcClaims:
        cleaned = request_headers(headers)
        token = authorization_bearer(cleaned)
        if token is None:
            raise AuthenticationError("missing bearer token")
        return self.verify(token)

    def verify(self, token: str) -> OidcClaims:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("malformed token")
        try:
            header = json.loads(_b64url_decode(parts[0]))
            payload = json.loads(_b64url_decode(parts[1]))
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuthenticationError("malformed token") from exc
        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise AuthenticationError("malformed token")
        alg = str(header.get("alg") or "")
        if alg not in ALLOWED_ALGS:
            raise AuthenticationError("token algorithm rejected")
        kid = str(header.get("kid") or "")
        key = self._key(kid)
        if key is None and not self._refreshed and self._jwks_loader is not None:
            self._jwks = self._jwks_loader()
            self._refreshed = True
            key = self._key(kid)
        if key is None:
            raise AuthenticationError("unknown signing key")
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        signature = _b64url_decode(parts[2])
        if not _verify(alg, key, signing_input, signature):
            raise AuthenticationError("invalid signature")
        return self._claims(payload)

    def _key(self, kid: str) -> dict[str, Any] | None:
        keys = self._jwks.get("keys")
        if not isinstance(keys, list):
            return None
        for item in keys:
            if isinstance(item, dict) and str(item.get("kid") or "") == kid:
                return item
        return None

    def _claims(self, payload: dict[str, Any]) -> OidcClaims:
        issuer = str(payload.get("iss") or "")
        subject = str(payload.get("sub") or "")
        audience = payload.get("aud")
        if isinstance(audience, list):
            audiences = {str(item) for item in audience}
        else:
            audiences = {str(audience or "")}
        exp = payload.get("exp")
        if issuer != self.config.issuer:
            raise AuthenticationError("issuer mismatch")
        if self.config.audience not in audiences:
            raise AuthenticationError("audience mismatch")
        if not subject:
            raise AuthenticationError("subject missing")
        if not isinstance(exp, int):
            raise AuthenticationError("expiry missing")
        expires = datetime.fromtimestamp(exp, tz=UTC)
        if expires + CLOCK_SKEW <= self._clock():
            raise AuthenticationError("token expired")
        nbf = payload.get("nbf")
        if isinstance(nbf, int):
            not_before = datetime.fromtimestamp(nbf, tz=UTC)
            if not_before - CLOCK_SKEW > self._clock():
                raise AuthenticationError("token not yet valid")
        return OidcClaims(issuer, subject, self.config.audience, expires)


def _verify(alg: str, key: dict[str, Any], message: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    try:
        if alg == "RS256":
            rsa.RSAPublicNumbers(_int(key["e"]), _int(key["n"])).public_key().verify(
                signature, message, padding.PKCS1v15(), hashes.SHA256()
            )
            return True
        if alg == "ES256":
            ec.EllipticCurvePublicNumbers(
                _int(key["x"]), _int(key["y"]), ec.SECP256R1()
            ).public_key().verify(signature, message, ec.ECDSA(hashes.SHA256()))
            return True
    except (InvalidSignature, KeyError, ValueError):
        return False
    return False


def _int(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("jwk integer")
    return int.from_bytes(_b64url_decode(value), "big")


def sign_rs256(payload: dict[str, Any], *, private_key: object, kid: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError("RSA private key required")
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": kid}).encode())
    body = _b64url(json.dumps(payload).encode())
    message = f"{header}.{body}".encode()
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{body}.{_b64url(signature)}"


def rsa_jwks(private_key: object, *, kid: str) -> Jwks:
    from cryptography.hazmat.primitives.asymmetric import rsa

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError("RSA private key required")
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }
