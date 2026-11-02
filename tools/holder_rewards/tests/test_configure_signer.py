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
