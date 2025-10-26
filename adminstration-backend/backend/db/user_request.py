from entities.User import User, UserHashedPassword
from utils.password import get_password_hash

async def get_user(username: str|None = None, password: str|None = None) -> User:
    if username is None and password is None:
        raise Exception("username and password are both None")
    if password is None:
        return User(id=1, name="Vitalya", email="i.shebanov@g.nsu.ru",
                     hashed_password=get_password_hash("123"), refresh_token="123")
    return User(id=1, name="Vitalya", email="i.shebanov@g.nsu.ru", hashed_password=get_password_hash("123"), refresh_token="123")
