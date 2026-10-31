"""Installer password hashing without importing Flask or touching the database."""
import base64
import hashlib
import secrets
import sys


def hash_password(value):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


if __name__ == '__main__':
    # The installer sends the password via stdin, never as a process argument.
    sys.stdout.write(hash_password(sys.stdin.read()))
