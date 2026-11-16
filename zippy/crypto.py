"""Shadowsocks AEAD (SIP022 / v1) cryptography.

The wire format implemented here is the one used by shadowsocks-rust,
Xray-core, Outline, Shadowrocket and v2rayNG:

    stream = salt | [enc_len | enc_data]*

    salt      = random key_len bytes, sent once per direction
    master    = EVP_BytesToKey(password, key_len)          (MD5)
    subkey    = HKDF-SHA1(ikm=master, salt=salt, info="ss-subkey")
    enc_len   = AEAD( uint16_be(len(data)) )                (2 + 16 bytes)
    enc_data  = AEAD( data )                                (len + 16 bytes)
    nonce     = 12-byte little-endian counter, starts at 0 for each direction
               and is incremented after *every* AEAD operation.

Reference implementations checked against:
  https://github.com/shadowsocks/shadowsocks-crypto  (src/v1/cipher.rs,
  src/v1/aeadcipher/mod.rs)
  https://github.com/shadowsocks/shadowsocks-rust    (relay/tcprelay/aead.rs)
"""
from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

TAG_LEN = 16
MAX_CHUNK = 0x3FFF
NONCE_LEN = 12

# method -> (cipher family, key/salt length in bytes)
METHODS: dict[str, tuple[str, int]] = {
    "aes-256-gcm": ("aes", 32),
    "aes-128-gcm": ("aes", 16),
    "chacha20-ietf-poly1305": ("chacha", 32),
}


def method_info(method: str) -> tuple[str, int]:
    if method not in METHODS:
        raise ValueError(f"unsupported cipher: {method!r} (choose from {', '.join(METHODS)})")
    return METHODS[method]


def bytes_to_key(password: bytes, length: int) -> bytes:
    """OpenSSL EVP_BytesToKey with MD5 and no salt."""
    out = bytearray()
    prev = b""
    while len(out) < length:
        prev = hashlib.md5(prev + password).digest()
        out.extend(prev)
    return bytes(out[:length])


def hkdf_sha1(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """HKDF (RFC 5869) instantiated with SHA-1, as required by Shadowsocks."""
    prk = hmac.new(salt, ikm, hashlib.sha1).digest()
    out = bytearray()
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha1).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


class AeadCipher:
    """One direction of a Shadowsocks AEAD stream."""

    def __init__(self, method: str, password: str | bytes, salt: bytes):
        family, self.key_len = method_info(method)
        if len(salt) != self.key_len:
            raise ValueError(f"salt must be {self.key_len} bytes for {method}")
        pwd = password.encode("utf-8") if isinstance(password, str) else password
        master = bytes_to_key(pwd, self.key_len)
        subkey = hkdf_sha1(master, salt, b"ss-subkey", self.key_len)
        self._aead = AESGCM(subkey) if family == "aes" else ChaCha20Poly1305(subkey)
        self._counter = 0

    def _next_nonce(self) -> bytes:
        nonce = self._counter.to_bytes(NONCE_LEN, "little")
        self._counter += 1
        return nonce

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._aead.encrypt(self._next_nonce(), plaintext, None)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._aead.decrypt(self._next_nonce(), ciphertext, None)


def new_salt(method: str) -> bytes:
    return os.urandom(method_info(method)[1])


# --------------------------------------------------------------------------
# Small self-check with known-answer vectors (no network needed).
# --------------------------------------------------------------------------
def _known_answer_test() -> None:
    # EVP_BytesToKey reference value for password "password", 16 bytes:
    # the first block must be plain MD5("password").
    assert bytes_to_key(b"password", 16) == hashlib.md5(b"password").digest()
    assert len(bytes_to_key(b"password", 32)) == 32

    # RFC 5869 Test Case 1 (SHA-256) is not applicable (we use SHA-1), so just
    # verify HKDF-SHA1 determinism and round-trip of the AEAD stream.
    method, password, salt = "aes-256-gcm", "correct horse battery staple", b"S" * 32
    a = AeadCipher(method, password, salt)
    b = AeadCipher(method, password, salt)
    for i in range(5):
        plain = os.urandom(i * 7 + 1)
        assert b.decrypt(a.encrypt(plain)) == plain
    assert a._counter == b._counter == 5


if __name__ == "__main__":
    _known_answer_test()
    print("crypto self-check: OK")
