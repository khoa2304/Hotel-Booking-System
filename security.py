import base64
import hashlib
import hmac
import os
import secrets


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    salt = os.urandom(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )

    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_hash = base64.b64encode(password_hash).decode("ascii")
    return f"scrypt${encoded_salt}${encoded_hash}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        algorithm, encoded_salt, encoded_hash = stored_password.split("$", 2)
        if algorithm != "scrypt":
            return False

        salt = base64.b64decode(encoded_salt)
        expected_hash = base64.b64decode(encoded_hash)
        actual_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        return hmac.compare_digest(actual_hash, expected_hash)
    except (ValueError, TypeError):
        return False


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_random_password() -> str:
    return secrets.token_urlsafe(10)
