"""Local certificate authority for the TLS man-in-the-middle.

For this to satisfy the Riot Client's certificate validation, the local CA's
certificate (root_ca.pem) needs to be trusted by the OS/runtime the client
uses -- exactly the same one-time step tools like `mkcert` ask you to do.
See README.md for the platform-specific commands.
"""
from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from .persistence import data_dir

CERT_DIR = data_dir() / "certs"
CA_KEY_PATH = CERT_DIR / "root_ca.key"
CA_CERT_PATH = CERT_DIR / "root_ca.pem"


def _write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def ensure_root_ca() -> Tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Load the local root CA, generating it on first run."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CA_KEY_PATH.exists() and CA_CERT_PATH.exists():
        key = serialization.load_pem_private_key(CA_KEY_PATH.read_bytes(), password=None)
        cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
        return key, cert

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Hallucinate Local CA")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    _write_private_key(CA_KEY_PATH, key)
    CA_CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def issue_leaf_certificate(hostname: str) -> Tuple[Path, Path]:
    """Issue (or reuse a cached) leaf cert/key for `hostname`, signed by the local CA.

    Returns (cert_path, key_path) suitable for ssl.SSLContext.load_cert_chain.
    """
    safe_name = hostname.replace("*", "_wildcard_")
    cert_path = CERT_DIR / f"{safe_name}.pem"
    key_path = CERT_DIR / f"{safe_name}.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    ca_key, ca_cert = ensure_root_ca()

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])

    san_entries: list = [x509.DNSName(hostname)]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(hostname)))
    except ValueError:
        pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    _write_private_key(key_path, leaf_key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
