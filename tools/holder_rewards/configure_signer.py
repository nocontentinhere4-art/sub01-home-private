#!/usr/bin/env python3
"""Import a Phantom Solana private key locally. Never activates payments."""
import argparse
import hashlib
import hmac
import warnings
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from solders.keypair import Keypair
from rewards import DEV, require


def save_signer(encoded, target):
    try:
        key = Keypair.from_base58_string(encoded.strip())
    except Exception:
        raise ValueError('Invalid Solana private key; no file written.') from None
    require(str(key.pubkey()) == DEV, 'Wrong wallet: expected the confirmed SUB-01 dev wallet. No file written.')
    target = Path(target)
    parent = target.parent.stat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.getuid() and not parent.st_mode & 0o077,
            'Signer directory must be owned by you and have permissions 0700.')
    # Exclusive creation: never overwrite an existing key or follow a target symlink.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(key.to_json() + '\n')
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return str(key.pubkey())


def slip10_seed(seed, indices):
    """SLIP-0010 Ed25519 hardened derivation; verified against published vectors."""
    node = hmac.new(b'ed25519 seed', seed, hashlib.sha512).digest()
    for index in indices:
        require(type(index) is int and 0 <= index < 2**31, 'Invalid derivation index')
        node = hmac.new(node[32:], b'\0' + node[:32] + (index + 2**31).to_bytes(4, 'big'), hashlib.sha512).digest()
    return node[:32]


def recovery_key(words):
    from mnemonic import Mnemonic
    phrase = ' '.join(words.strip().split())
    require(len(phrase.split()) in (12, 15, 18, 21, 24), 'Invalid recovery phrase length')
    try:
        language = Mnemonic.detect_language(phrase)
        require(Mnemonic(language).check(phrase), 'Invalid recovery phrase checksum')
    except Exception:
        raise ValueError('Invalid recovery phrase; no file written.') from None
    seed = Mnemonic.to_seed(phrase, passphrase='')
    # Common Solana wallet paths. Match the exact expected public key, never guess.
    paths = [(44, 501)]
    for index in range(100):
        paths.extend([(44, 501, index, 0), (44, 501, index), (44, 501, 0, index)])
    for path in dict.fromkeys(paths):
        key = Keypair.from_seed(slip10_seed(seed, path))
        if str(key.pubkey()) == DEV:
            return str(key)
    legacy = Keypair.from_seed(seed[:32])
    if str(legacy.pubkey()) == DEV:
        return str(legacy)
    raise ValueError('Dev wallet not found; no file written. Imported accounts or a separate passphrase may use a different seed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', action='store_true')
    args = parser.parse_args()
    warnings.simplefilter('error', getpass.GetPassWarning)
    os.umask(0o077)
    require(sys.stdin.isatty(), 'Run this yourself in a local Terminal, not through chat or a pipe.')
    root = Path.home() / 'Library/Application Support/SUB01Rewards'
    config = json.loads((root / 'config.json').read_text())
    print('SUB-01 local signer setup — no transactions will be sent.')
    print('This gives the local service full signing access to the DEV wallet.')
    print('Expected wallet: ' + DEV)
    if args.recovery:
        print('Recovery mode: enter your recovery words ONLY at the hidden prompt below.')
        print('This command makes no network calls and saves only the matching DEV private key, not the recovery words.')
    else:
        print('Enter only the Solana PRIVATE KEY exported from Phantom, never the recovery phrase.')
    print('Input is hidden. Do not paste it into a command line or chat.')
    secret = getpass.getpass('Recovery words (hidden): ' if args.recovery else 'Private key (hidden): ')
    try:
        if args.recovery:
            secret = recovery_key(secret)
        wallet = save_signer(secret, config['keypair_file'])
    finally:
        secret = None
    print('Saved locally with permissions 0600; wallet verified: ' + wallet)
    print('Payments remain disabled. Close the private-key view in Phantom and clear your clipboard.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Cancelled; payments remain disabled.')
    except Exception:
        # Never include exception text: third-party parsers may echo sensitive input.
        raise SystemExit('Setup refused. Check the wallet, file permissions, or whether a signer already exists. Payments remain disabled.')
