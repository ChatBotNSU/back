from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def verify_password(plain_password, hashed_password):
    print(password_hash.hash(plain_password))
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)
