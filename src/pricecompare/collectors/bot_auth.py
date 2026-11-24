"""Web Bot Auth (RFC 9421 signatures): the reader says who it is, so a shop can verify it is DerbaniBot and give it the
limits meant for signed readers (Shopify asks for this in its shops' agents.md). Owner's yes: 2026-11-25.

The private key is only in BOT_KEY_FILE on the owner's PC (and as a secret of the derbani-home worker, which publishes
the public half at https://derbani.com/.well-known/http-message-signatures-directory). No key file: nothing is signed.
A signature never changes the rules: robots.txt, the pace and the rests after a refusal stay as they are."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

BOT_KEY_FILE = Path.home() / ".derbani" / "bot_key.json"   # an Ed25519 key as JWK
AGENT = "https://derbani.com"
LIFE = 60                                                  # seconds one signature is valid


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def key_id(jwk: dict) -> str:
    """RFC 7638 / 8037 thumbprint of the public key."""
    public = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]}, separators=(",", ":"))
    return b64u(hashlib.sha256(public.encode()).digest())


def new_key() -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    return {"kty": "OKP", "crv": "Ed25519", "x": b64u(k.public_key().public_bytes_raw()), "d": b64u(k.private_bytes_raw())}


class Signer:
    """An httpx request hook: signs each request (and each redirect) for the host it really goes to."""

    def __init__(self, jwk: dict):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.key = Ed25519PrivateKey.from_private_bytes(unb64u(jwk["d"]))
        self.key_id = key_id(jwk)

    def __call__(self, request) -> None:
        now = int(time.time())
        agent = f'"{AGENT}"'
        nonce = base64.b64encode(os.urandom(32)).decode()
        params = (f'("@authority" "signature-agent");created={now};keyid="{self.key_id}";alg="ed25519";'
                  f'expires={now + LIFE};nonce="{nonce}";tag="web-bot-auth"')
        host = request.headers["host"].lower()   # httpx leaves out the usual port
        base = f'"@authority": {host}\n"signature-agent": {agent}\n"@signature-params": {params}'
        signature = base64.b64encode(self.key.sign(base.encode("ascii"))).decode()
        request.headers["Signature-Agent"] = agent
        request.headers["Signature-Input"] = f"sig1={params}"
        request.headers["Signature"] = f"sig1=:{signature}:"


def signer(path: Path | None = None) -> Signer | None:
    path = path or BOT_KEY_FILE
    if not path.exists():
        return None
    return Signer(json.loads(path.read_text(encoding="utf-8")))
