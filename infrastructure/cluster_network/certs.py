# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Self-signed X.509 certificate generation for node-to-node mTLS.

In a Stage-2 demo with a small, manually-configured set of nodes, each
node's own self-signed certificate acts as its own trust root (added to
peers' trust bundles out-of-band via `trust_store.py`). A production
deployment would replace this with certs issued by an internal CA — the
rest of the network layer does not need to change for that upgrade.
"""

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_self_signed_cert(node_id: str) -> tuple[bytes, bytes]:
    """Returns (cert_pem, key_pem) for a node identified by `node_id`."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)])
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.DNSName(node_id)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def certificate_common_name(cert_pem: str) -> str:
    """Return the single subject CN of a PEM certificate.

    Trust bootstrap receives a certificate over an untrusted channel.  This
    helper lets the receiver derive the transport identity from that public
    certificate instead of trusting a JSON field that merely *claims* it.
    """
    certificate = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    values = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(values) != 1 or not values[0].value.strip():
        raise ValueError("certificate must contain exactly one non-empty common name")
    return values[0].value
