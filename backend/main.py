import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend.database import engine, SessionLocal
from backend.models import Base, Business, User
from backend.config import settings
from backend.api import router
from backend.booking import cleanup_expired_holds
from bot.runner import start_bot

app = FastAPI(title="EasyBook", version="0.2.0")
app.include_router(router)
BASE = Path(__file__).resolve().parents[1]
app.mount("/app", StaticFiles(directory=BASE / "miniapp", html=True), name="miniapp")


async def cleanup_loop():
    while True:
        try:
            async with SessionLocal() as db:
                await cleanup_expired_holds(db)
        except Exception as exc:
            print("hold cleanup error:", exc)
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        q = await db.execute(select(Business).limit(1))
        business = q.scalar_one_or_none()
        if not business:
            db.add(Business(timezone="Europe/Moscow"))

        q = await db.execute(select(User).where(User.telegram_id == settings.owner_telegram_id))
        owner = q.scalar_one_or_none()
        if not owner:
            db.add(User(telegram_id=settings.owner_telegram_id, full_name="Owner", role="owner"))
        else:
            owner.role = "owner"
        await db.commit()

    app.state.bot_task = asyncio.create_task(start_bot())
    app.state.cleanup_task = asyncio.create_task(cleanup_loop())


@app.on_event("shutdown")
async def shutdown():
    for name in ("bot_task", "cleanup_task"):
        task = getattr(app.state, name, None)
        if task:
            task.cancel()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
