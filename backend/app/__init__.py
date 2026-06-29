# Lumen Backend Application Package
import bcrypt

# Monkeypatch bcrypt to truncate passwords longer than 72 bytes.
# This prevents passlib from crashing with modern bcrypt (4.1+) on Python 3.13.
original_hashpw = bcrypt.hashpw

def patched_hashpw(password, salt):
    if isinstance(password, bytes) and len(password) > 72:
        password = password[:72]
    elif isinstance(password, str):
        encoded = password.encode('utf-8')
        if len(encoded) > 72:
            password = encoded[:72]
    return original_hashpw(password, salt)

bcrypt.hashpw = patched_hashpw
