import unittest, tempfile, os, sys
from pathlib import Path
from unittest.mock import patch
from solders.keypair import Keypair
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configure_signer as c

class SignerTests(unittest.TestCase):
    def test_wrong_wallet_leaves_no_key(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'key.json'
            with self.assertRaises(ValueError):c.save_signer(str(Keypair()),target)
            self.assertFalse(target.exists())
    def test_private_permissions_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            key=Keypair();target=Path(d)/'key.json'
            with patch.object(c,'DEV',str(key.pubkey())):
                c.save_signer(str(key),target)
                self.assertEqual(target.stat().st_mode & 0o777,0o600)
                self.assertEqual(Keypair.from_json(target.read_text()).pubkey(),key.pubkey())
                original=target.read_bytes()
                with self.assertRaises(FileExistsError):c.save_signer(str(key),target)
                self.assertEqual(original,target.read_bytes())
    def test_invalid_input_not_echoed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as e:c.save_signer('secret-invalid-input',Path(d)/'key')
            self.assertNotIn('secret-invalid-input',str(e.exception))

class RecoveryTests(unittest.TestCase):
    def test_official_slip10_ed25519_vectors(self):
        seed=bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        self.assertEqual(c.slip10_seed(seed,()).hex(),'2b4be7f19ee27bbf30c667b642d5f4aa69fd169872f8fc3059c08ebae2eb19e7')
        self.assertEqual(c.slip10_seed(seed,(0,1)).hex(),'b1d0bad404bf35da785a64ca1ac54b2617211d2777696fbffaf208f746ae84f2')
    def test_recovery_finds_only_matching_wallet(self):
        from mnemonic import Mnemonic
        # PUBLIC, standard BIP39 test fixture, never a real wallet.
        words=Mnemonic('english').to_mnemonic(bytes(32))
        seed=Mnemonic.to_seed(words)
        expected=Keypair.from_seed(c.slip10_seed(seed,(44,501,3,0)))
        with patch.object(c,'DEV',str(expected.pubkey())):
            self.assertEqual(Keypair.from_base58_string(c.recovery_key(words)).pubkey(),expected.pubkey())
        with self.assertRaises(ValueError):c.recovery_key(words)
    def test_bad_checksum_rejected(self):
        with self.assertRaises(ValueError):c.recovery_key('abandon '*24)
