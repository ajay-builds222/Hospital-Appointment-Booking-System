
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db, settings
from app.models.models import RefreshToken, User
from app.schemas.schemas import LoginIn, RegisterIn
from app.services.email_service import send_email


router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=401,
                detail="Invalid access token",
            )

        user = db.get(User, int(payload["sub"]))

    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Inactive or unknown user",
        )

    return user


def require_roles(*roles):
    def checker(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )
        return user

    return checker


@router.post("/register", status_code=201)
def register(
    data: RegisterIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user = User(
        email=str(data.email),
        full_name=data.full_name,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role="patient",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    background_tasks.add_task(
        send_email,
        user.email,
        "Welcome",
        "Your patient account has been created.",
    )

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(
        data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Inactive user",
        )

    access, _ = create_token(
        user.id,
        "access",
        timedelta(minutes=settings.access_token_minutes),
    )

    refresh, payload = create_token(
        user.id,
        "refresh",
        timedelta(days=settings.refresh_token_days),
    )

    # JWT exp is an integer Unix timestamp, not a datetime object.
    expires_at = datetime.fromtimestamp(
        payload["exp"], tz=timezone.utc
    ).replace(tzinfo=None)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_jti=payload["jti"],
            expires_at=expires_at,
            revoked=False,
        )
    )
    db.commit()

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
    }


@router.post("/refresh")
def refresh_token(body: dict, db: Session = Depends(get_db)):
    token = body.get("refresh_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token required",
        )

    try:
        payload = decode_token(token)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_jti == payload["jti"],
                RefreshToken.revoked.is_(False),
            )
            .first()
        )

        user = db.get(User, int(payload["sub"]))

        if (
            not stored
            or stored.expires_at < datetime.utcnow()
            or not user
            or not user.is_active
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token expired or revoked",
            )

        access, _ = create_token(
            user.id,
            "access",
            timedelta(minutes=settings.access_token_minutes),
        )

        return {
            "access_token": access,
            "token_type": "bearer",
            "expires_in": settings.access_token_minutes * 60,
        }

    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )


@router.post("/logout")
def logout(body: dict, db: Session = Depends(get_db)):
    token = body.get("refresh_token")

    if not token:
        raise HTTPException(
            status_code=400,
            detail="Refresh token required",
        )

    try:
        payload = decode_token(token)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_jti == payload["jti"]
            )
            .first()
        )

        if stored:
            stored.revoked = True
            db.commit()

        return {"message": "Logged out"}

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token",
        )


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }
