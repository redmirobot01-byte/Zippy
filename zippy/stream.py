"""Shadowsocks AEAD chunked stream (both client and server side)."""
from __future__ import annotations

import asyncio
import logging

from .common import ProtocolError, read_exact
from .crypto import MAX_CHUNK, TAG_LEN, AeadCipher, method_info, new_salt

log = logging.getLogger("zippy.ss")


class SSStream:
    """A decrypted/plain view over one Shadowsocks TCP connection.

    Server: ``accept()`` reads the client salt and immediately writes its own.
    Client: ``connect()`` writes its salt; the server salt is read lazily on
            the first downstream chunk.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 method: str, password: str):
        self.reader = reader
        self.writer = writer
        self.method = method
        self.password = password
        self.salt_len = method_info(method)[1]
        self.dec: AeadCipher | None = None
        self.enc: AeadCipher | None = None
        self._buf = bytearray()

    @classmethod
    async def accept(cls, reader, writer, method: str, password: str) -> "SSStream":
        salt = await read_exact(reader, method_info(method)[1])
        self = cls(reader, writer, method, password)
        self.dec = AeadCipher(method, password, salt)
        server_salt = new_salt(method)
        self.enc = AeadCipher(method, password, server_salt)
        writer.write(server_salt)
        await writer.drain()
        return self

    @classmethod
    async def connect(cls, reader, writer, method: str, password: str) -> "SSStream":
        self = cls(reader, writer, method, password)
        client_salt = new_salt(method)
        self.enc = AeadCipher(method, password, client_salt)
        writer.write(client_salt)
        await writer.drain()
        return self

    async def read_chunk(self) -> bytes | None:
        """Return one decrypted data chunk; None means clean EOF."""
        if self.dec is None:
            try:
                salt = await read_exact(self.reader, self.salt_len)
            except EOFError:
                return None
            self.dec = AeadCipher(self.method, self.password, salt)
        try:
            len_ct = await read_exact(self.reader, 2 + TAG_LEN)
        except EOFError:
            return None
        try:
            size = int.from_bytes(self.dec.decrypt(len_ct), "big")
        except Exception as exc:  # InvalidTag
            raise ProtocolError("bad AEAD tag on length chunk") from exc
        if size > MAX_CHUNK:
            raise ProtocolError(f"chunk too large: {size}")
        try:
            ct = await read_exact(self.reader, size + TAG_LEN)
        except EOFError as exc:
            raise ProtocolError("truncated data chunk") from exc
        try:
            return self.dec.decrypt(ct)
        except Exception as exc:
            raise ProtocolError("bad AEAD tag on data chunk") from exc

    async def read_plain(self, n: int) -> bytes:
        """Read exactly n plaintext bytes, transparently crossing chunk edges."""
        while len(self._buf) < n:
            chunk = await self.read_chunk()
            if chunk is None:
                raise ProtocolError("EOF while reading header")
            self._buf.extend(chunk)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def take_remaining(self) -> bytes:
        """Consume plaintext already decrypted (initial request payload)."""
        out = bytes(self._buf)
        self._buf.clear()
        return out

    async def write_plain(self, data: bytes) -> None:
        if self.enc is None:
            raise ProtocolError("stream not initialised for writing")
        if not data:
            return
        for i in range(0, len(data), MAX_CHUNK):
            chunk = data[i:i + MAX_CHUNK]
            self.writer.write(self.enc.encrypt(len(chunk).to_bytes(2, "big")))
            self.writer.write(self.enc.encrypt(chunk))
        await self.writer.drain()
