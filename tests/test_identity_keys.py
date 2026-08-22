"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

أول اختبارات مباشرة لـ infrastructure/cognitive_core/identity/keys.py —
البدائل التشفيرية (Ed25519) التي تُوقِّع كل استدعاء بين الطبقات ويُدقَّق
عليها. كانت 60% مغطاة فقط رغم أنها الأساس الذي يُبنى عليه أي ضمان أمان
لاحق (توقيع، تدقيق، هوية عقدة). يغطي هذا الملف خصائص الأمان الجوهرية،
لا فقط "الاستدعاء لا يرمي استثناءً":

- جولة توقيع/تحقق كاملة تنجح مع المفتاح الصحيح.
- تعديل حرف واحد في الحمولة يُفشل التحقق (كشف العبث الفعلي).
- التحقق بمفتاح عام خاطئ يُفشل التحقق (لا قبول عرضي).
- جولة تصدير/استيراد المفتاح الخاص عبر hex تُعيد نفس زوج المفاتيح فعليًا
  (لا فقط "لا يرمي استثناءً" — بل يوقّع/يتحقق بشكل متبادل صحيح).
- `is_valid` غلاف بولياني صحيح للنجاح والفشل معًا.
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

        verify(keypair.public_key_hex, payload, signature)  # لا يرمي = نجاح

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
        # يجب أن يتحقق المفتاح المُعاد بناؤه من نفس التوقيع دون استثناء
        reconstructed_public.verify(signature, payload)

    def test_private_key_hex_roundtrip_preserves_signing_ability(self):
        """جولة تصدير/استيراد المفتاح الخاص (مطلوبة لهوية عقدة ثابتة عبر
        إعادة التشغيل، راجع توثيق الدالة) — يجب أن يبقى المفتاح المُعاد
        بناؤه قادرًا على توقيع محتوى يتحقق منه المفتاح العام الأصلي."""
        original = generate_keypair()
        restored = keypair_from_private_hex(original.private_key_hex)

        self.assertEqual(restored.public_key_hex, original.public_key_hex)

        payload = b"signed after restart"
        signature = restored.sign(payload)
        verify(original.public_key_hex, payload, signature)  # لا يرمي = نجاح


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
