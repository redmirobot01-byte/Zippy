"""Self-signed TLS certificate generation (no openssl binary required)."""
from __future__ import annotations

import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed(host: str, cert_path: str, key_path: str, days: int = 3650) -> None:
    cert_p, key_p = Path(cert_path), Path(key_path)
    cert_p.parent.mkdir(parents=True, exist_ok=True)
    key_p.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Zippy"),
        x509.NameAttribute(NameOID.COMMON_NAME, host),
    ])
    san: list[x509.GeneralName] = []
    try:
        san.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        san.append(x509.DNSName(host))
    san.append(x509.DNSName("localhost"))

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_p.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    os.chmod(key_p, 0o600)
