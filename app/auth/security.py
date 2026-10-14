from datetime import datetime, timedelta, timezone
from uuid import uuid4
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.database import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_token(user_id: int, token_type: str, expires: timedelta):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": token_type, "jti": uuid4().hex,
               "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM), payload

def decode_token(token: str):
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
