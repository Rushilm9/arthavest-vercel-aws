def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    For development simplicity: just compares plain text passwords.
    """
    return plain_password == hashed_password


def get_password_hash(password: str) -> str:
    """
    For development simplicity: just returns the plain text password.
    NO HASHING.
    """
    return password
