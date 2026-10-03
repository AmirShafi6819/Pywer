import unittest
from pywer.crypto.aes import AESCTR
from pywer.crypto.ec import ec_keygen, ec_on_curve, ecdh, pub_to_spki, spki_to_pub


class TestCrypto(unittest.TestCase):
    def test_aes_ctr_roundtrip(self):
        key = b"\x01" * 32
        iv = b"\x02" * 16
        plaintext = b"Hello, Minecraft Bedrock 1.21.50 network packet payload!"

        cipher_enc = AESCTR(key, iv)
        ciphertext = cipher_enc.process(plaintext)
        self.assertNotEqual(ciphertext, plaintext)

        cipher_dec = AESCTR(key, iv)
        decrypted = cipher_dec.process(ciphertext)
        self.assertEqual(decrypted, plaintext)

    def test_ec_p384_keygen_and_ecdh(self):
        # Generate two key pairs
        priv_a, pub_a = ec_keygen()
        priv_b, pub_b = ec_keygen()

        self.assertTrue(ec_on_curve(pub_a))
        self.assertTrue(ec_on_curve(pub_b))

        # Test SPKI serialization
        der_a = pub_to_spki(pub_a)
        parsed_pub_a = spki_to_pub(der_a)
        self.assertEqual(pub_a, parsed_pub_a)

        # Test ECDH shared secret derivation
        secret_ab = ecdh(priv_a, pub_b)
        secret_ba = ecdh(priv_b, pub_a)
        self.assertEqual(secret_ab, secret_ba)
        self.assertEqual(len(secret_ab), 48)


if __name__ == "__main__":
    unittest.main()
