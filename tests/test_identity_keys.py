"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

First direct tests for infrastructure/cognitive_core/identity/keys.py—the
Ed25519 cryptographic primitives that sign and verify every cross-layer call.
They had only 60% coverage despite forming the basis for subsequent security
guarantees (signing, audit, and node identity). This file covers core security
properties, not merely whether calls raise no exception:

- A complete signing and verification round trip succeeds with the correct key.
- Modifying one byte of the payload fails verification (real tamper detection).
- Verification with the wrong public key fails (no accidental acceptance).
- A private-key hex export/import round trip recreates the same keypair in
  practice—not merely without raising, but with correct mutual signing and verification.
- `is_valid` is a correct Boolean wrapper for both success and failure.
"""
from __future__ import annotations

import unittest

from infrastructure.cognitive_core.identity.exceptions import InvalidSignatureError
from infrastructure.cognitive_core.identity.keys import (
    generate_keypair,
    is_valid,
    keypair_from_private_hex,
    public_key_from_hex,
    verify,
)


class TestKeyGenerationAndSigning(unittest.TestCase):
    def test_sign_then_verify_succeeds_with_correct_key(self):
        keypair = generate_keypair()
        payload = b"transfer authority to node-b"
        signature = keypair.sign(payload)

        verify(keypair.public_key_hex, payload, signature)  # No exception means success.

    def test_tampered_payload_fails_verification(self):
        keypair = generate_keypair()
        signature = keypair.sign(b"original payload")

        with self.assertRaises(InvalidSignatureError):
            verify(keypair.public_key_hex, b"tampered payload", signature)

    def test_verification_with_wrong_public_key_fails(self):
        signer = generate_keypair()
        impostor = generate_keypair()
        payload = b"approve deployment"
        signature = signer.sign(payload)

        with self.assertRaises(InvalidSignatureError):
            verify(impostor.public_key_hex, payload, signature)

    def test_two_generated_keypairs_are_never_identical(self):
        a = generate_keypair()
        b = generate_keypair()
        self.assertNotEqual(a.public_key_hex, b.public_key_hex)
        self.assertNotEqual(a.private_key_hex, b.private_key_hex)


class TestHexSerializationRoundtrips(unittest.TestCase):
    def test_public_key_hex_roundtrips_and_verifies(self):
        keypair = generate_keypair()
        payload = b"some payload"
        signature = keypair.sign(payload)

        reconstructed_public = public_key_from_hex(keypair.public_key_hex)
        # The reconstructed key must verify the same signature without error.
        reconstructed_public.verify(signature, payload)

    def test_private_key_hex_roundtrip_preserves_signing_ability(self):
        """A private-key export/import round trip is required for stable node
        identity across restarts; see the function documentation. The restored
        key must remain able to sign content that the original public key verifies."""
        original = generate_keypair()
        restored = keypair_from_private_hex(original.private_key_hex)

        self.assertEqual(restored.public_key_hex, original.public_key_hex)

        payload = b"signed after restart"
        signature = restored.sign(payload)
        verify(original.public_key_hex, payload, signature)  # No exception means success.


class TestIsValidBooleanWrapper(unittest.TestCase):
    def test_returns_true_for_a_valid_signature(self):
        keypair = generate_keypair()
        payload = b"payload"
        signature = keypair.sign(payload)
        self.assertTrue(is_valid(keypair.public_key_hex, payload, signature))

    def test_returns_false_instead_of_raising_for_invalid_signature(self):
        keypair = generate_keypair()
        signature = keypair.sign(b"real payload")
        self.assertFalse(is_valid(keypair.public_key_hex, b"different payload", signature))


if __name__ == "__main__":
    unittest.main()
