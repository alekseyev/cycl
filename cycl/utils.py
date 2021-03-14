import secrets
import string

ALPHABET = string.ascii_letters + string.digits
PASSWORD_LENGTH = 16


def gen_password():
    return "".join(secrets.choice(ALPHABET) for i in range(PASSWORD_LENGTH))
