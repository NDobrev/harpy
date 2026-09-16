"""Deployment key ring and AES-256-GCM credential wrapping."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyRing:
    active_id: str
    keys: dict[str, bytes]


def load_keyring(path: Path) -> KeyRing:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretError(f"key ring is unreadable: {path}") from exc
    if not isinstance(loaded, dict):
        raise SecretError("key ring is corrupt")
    active = str(loaded.get("active") or "")
    raw_keys = loaded.get("keys")
    if not active or not isinstance(raw_keys, dict) or active not in raw_keys:
        raise SecretError("key ring is corrupt")
    keys: dict[str, bytes] = {}
    for key_id, value in raw_keys.items():
        material = bytes.fromhex(str(value))
        if len(material) != 32:
            raise SecretError("key ring key must be 32 bytes")
        keys[str(key_id)] = material
    return KeyRing(active, keys)


def write_keyring(path: Path, ring: KeyRing) -> None:
    payload = {
        "active": ring.active_id,
        "keys": {key_id: material.hex() for key_id, material in ring.keys.items()},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def generate_keyring() -> KeyRing:
    return KeyRing("k1", {"k1": secrets.token_bytes(32)})


def associated_data(
    *,
    tenant_id: UUID,
    credential_id: UUID,
    owner_user_id: UUID | None,
    kind: str,
    version: int,
) -> bytes:
    owner = str(owner_user_id) if owner_user_id is not None else "none"
    return f"{tenant_id}:{credential_id}:{owner}:{kind}:{version}".encode()


def encrypt_secret(ring: KeyRing, plaintext: bytes, aad: bytes) -> tuple[str, str, str]:
    nonce = secrets.token_bytes(12)
    token = AESGCM(ring.keys[ring.active_id]).encrypt(nonce, plaintext, aad)
    return token.hex(), nonce.hex(), ring.active_id


def decrypt_secret(ring: KeyRing, *, ciphertext: str, nonce: str, key_id: str, aad: bytes) -> bytes:
    material = ring.keys.get(key_id)
    if material is None:
        raise SecretError("unknown key id")
    try:
        return AESGCM(material).decrypt(bytes.fromhex(nonce), bytes.fromhex(ciphertext), aad)
    except Exception as exc:
        raise SecretError("credential cannot be decrypted") from exc


def hosted_github_environ(token: str) -> dict[str, str]:
    return {
        "GH_TOKEN": token,
        "GH_CONFIG_DIR": "/var/empty/harpy-gh",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GH_NO_UPDATE_NOTIFIER": "1",
    }


def refuse_ambient_github(environ: Mapping[str, str] | None = None) -> None:
    env = environ if environ is not None else os.environ
    if env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"):
        raise SecretError("hosted mode must not use ambient GitHub credentials")
