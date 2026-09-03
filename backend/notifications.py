from aiogram import Bot
from sqlalchemy import select

from backend.config import settings
from backend.models import User, Staff, BookingItem, Service
from backend.timeutils import utc_naive_to_local


async def notify_admins_booking_event(db, booking, business, title: str):
    uq = await db.execute(select(User).where(User.role.in_(["owner", "admin"]), User.is_active == True))
    users = uq.scalars().all()
    client = await db.get(User, booking.client_user_id)
    staff = await db.get(Staff, booking.staff_id)
    iq = await db.execute(
        select(Service.name)
        .join(BookingItem, BookingItem.service_id == Service.id)
        .where(BookingItem.booking_id == booking.id)
    )
    services = ", ".join(iq.scalars().all())
    local = utc_naive_to_local(booking.start_at, business.timezone)
    status = {
        "confirmed": "подтверждена",
        "temporary_hold": f"ждёт подтверждения, удержание {business.hold_minutes} мин",
        "cancelled_client": "отменена клиентом",
        "cancelled_admin": "отменена администратором",
    }.get(booking.status, booking.status)
    text = (
        f"{title} #{booking.id}\n\n"
        f"👤 {client.full_name}\n"
        f"📞 {client.phone or 'не указан'}\n"
        f"✨ {services}\n"
        f"🧑‍💼 {staff.display_name}\n"
        f"🕐 {local:%d.%m.%Y %H:%M}\n"
        f"📌 {status}"
    )
    bot = Bot(settings.bot_token)
    try:
        for user in users:
            try:
                await bot.send_message(user.telegram_id, text)
            except Exception:
                pass
    finally:
        await bot.session.close()


async def notify_admins_new_booking(db, booking, business):
    await notify_admins_booking_event(db, booking, business, "📅 Новая запись")


async def notify_client_status(db, booking, business, text_prefix: str):
    client = await db.get(User, booking.client_user_id)
    staff = await db.get(Staff, booking.staff_id)
    if not client or client.telegram_id <= 0:
        return
    local = utc_naive_to_local(booking.start_at, business.timezone)
    bot = Bot(settings.bot_token)
    try:
        await bot.send_message(
            client.telegram_id,
            f"{text_prefix}\n\n🧑‍💼 {staff.display_name}\n🕐 {local:%d.%m.%Y %H:%M}",
        )
    except Exception:
        pass
    finally:
        await bot.session.close()
