import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import User

MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


def validate_telegram_init_data(init_data: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing Telegram hash")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram initData")

    auth_date = int(pairs.get("auth_date", "0") or 0)
    if auth_date and time.time() - auth_date > MAX_AUTH_AGE_SECONDS:
        raise ValueError("Telegram authorization data is too old")

    if "user" in pairs:
        pairs["user"] = json.loads(pairs["user"])
    return pairs


async def current_user(
    x_telegram_init_data: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if settings.dev_mode and not x_telegram_init_data:
        telegram_user = {"id": settings.owner_telegram_id, "first_name": "Dev Owner"}
    else:
        if not x_telegram_init_data:
            raise HTTPException(401, "Open EasyBook from Telegram")
        try:
            data = validate_telegram_init_data(x_telegram_init_data)
            telegram_user = data.get("user") or {}
        except Exception as exc:
            raise HTTPException(401, str(exc)) from exc

    telegram_id = int(telegram_user.get("id", 0))
    if not telegram_id:
        raise HTTPException(401, "Telegram user is missing")

    q = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = q.scalar_one_or_none()
    full_name = " ".join(
        part for part in [telegram_user.get("first_name"), telegram_user.get("last_name")] if part
    ).strip()

    if not user:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name or "Telegram user",
            role="owner" if telegram_id == settings.owner_telegram_id else "client",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif full_name and user.full_name != full_name:
        user.full_name = full_name
        if telegram_id == settings.owner_telegram_id:
            user.role = "owner"
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(403, "Account is disabled")
    return user


def require_roles(*roles: str):
    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Not enough permissions")
        return user
    return dependency
