import httpx

from entities.User import User, UserHashedPassword
from utils.password import get_password_hash
from config import get_config

config = get_config()

url = f"http://{config.db_service.host}:{config.db_service.port}/api/v1/user"

async def get_user(email: str|None = None, password: str|None = None) -> User:
    if email is None and password is None:
        raise Exception("username and password are both None")

    result = None
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{url}/get_by_email", params={"email": email})
        r.raise_for_status()
        result = r.json()
    
    print(result)
    return User(**result)



