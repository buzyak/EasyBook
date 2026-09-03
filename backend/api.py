from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import (
    Business, User, Staff, Service, StaffService, WeeklySchedule, ScheduleException,
    BlockedInterval, Booking, BookingItem, BookingHistory,
)
from backend.schemas import *
from backend.security import current_user, require_roles
from backend.booking import create_booking, available_slots, get_business, get_specs, slot_is_free
from backend.notifications import notify_admins_new_booking, notify_admins_booking_event, notify_client_status
from backend.timeutils import aware_to_utc_naive, utc_naive_to_local, utc_naive_iso

router = APIRouter(prefix="/api")
admin_user = require_roles("owner", "admin")
manager_user = require_roles("owner", "admin", "performer")


def user_dict(user: User):
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
    }


async def booking_dict(db: AsyncSession, booking: Booking, business: Business):
    client = await db.get(User, booking.client_user_id)
    staff = await db.get(Staff, booking.staff_id)
    iq = await db.execute(
        select(BookingItem, Service)
        .join(Service, Service.id == BookingItem.service_id)
        .where(BookingItem.booking_id == booking.id)
        .order_by(BookingItem.id)
    )
    services = [
        {
            "id": service.id,
            "name": service.name,
            "duration_minutes": item.duration_minutes,
            "price": item.price,
        }
        for item, service in iq.all()
    ]
    return {
        "id": booking.id,
        "status": booking.status,
        "start_at": utc_naive_iso(booking.start_at),
        "end_at": utc_naive_iso(booking.end_at),
        "local_start": utc_naive_to_local(booking.start_at, business.timezone).isoformat(),
        "local_end": utc_naive_to_local(booking.end_at, business.timezone).isoformat(),
        "hold_expires_at": utc_naive_iso(booking.hold_expires_at) if booking.hold_expires_at else None,
        "client": user_dict(client),
        "staff": {"id": staff.id, "display_name": staff.display_name},
        "services": services,
    }


@router.get("/health")
async def health():
    return {"ok": True, "name": "EasyBook"}


@router.get("/me")
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    business = await get_business(db)
    staff_id = None
    if user.role == "performer":
        sq = await db.execute(select(Staff.id).where(Staff.user_id == user.id))
        staff_id = sq.scalar_one_or_none()
    return {
        "user": user_dict(user),
        "staff_id": staff_id,
        "business": {
            "id": business.id,
            "name": business.name,
            "timezone": business.timezone,
            "currency": business.currency,
            "is_onboarded": business.is_onboarded,
            "booking_confirmation_mode": business.booking_confirmation_mode,
            "hold_minutes": business.hold_minutes,
            "slot_step_minutes": business.slot_step_minutes,
            "allow_client_cancel": business.allow_client_cancel,
            "cancel_before_hours": business.cancel_before_hours,
            "allow_client_reschedule": business.allow_client_reschedule,
            "reschedule_before_hours": business.reschedule_before_hours,
            "booking_horizon_days": business.booking_horizon_days,
        },
    }


@router.post("/setup")
async def setup(
    data: BusinessSetupIn,
    _: User = Depends(require_roles("owner")),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business(db)
    business.name = data.name
    business.timezone = data.timezone or "Europe/Moscow"
    business.currency = data.currency or None
    business.is_onboarded = True
    await db.commit()
    await db.refresh(business)
    return business


@router.patch("/business/settings")
async def patch_business(
    data: BusinessSettingsPatch,
    _: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_business(db)
    patch = data.model_dump(exclude_unset=True)
    if patch.get("booking_confirmation_mode") not in {None, "manual", "auto"}:
        raise HTTPException(400, "confirmation mode must be manual or auto")
    for key, value in patch.items():
        setattr(business, key, value)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/services")
async def services(
    active_only: bool = True,
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Service).order_by(Service.name)
    if active_only:
        stmt = stmt.where(Service.is_active == True)
    q = await db.execute(stmt)
    return q.scalars().all()


@router.post("/services")
async def service_create(
    data: ServiceCreate,
    _: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = Service(
        name=data.name,
        description=data.description,
        default_duration_minutes=data.default_duration_minutes,
        default_price=data.default_price,
    )
    db.add(service)
    await db.flush()
    for staff_id in list(dict.fromkeys(data.staff_ids)):
        db.add(StaffService(staff_id=staff_id, service_id=service.id))
    await db.commit()
    await db.refresh(service)
    return service


@router.patch("/services/{service_id}")
async def service_patch(service_id: int, data: ServicePatch, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    await db.commit()
    await db.refresh(service)
    return service


@router.get("/services/{service_id}/staff")
async def service_staff(service_id: int, _: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    q = await db.execute(
        select(StaffService, Staff)
        .join(Staff, Staff.id == StaffService.staff_id)
        .where(StaffService.service_id == service_id, StaffService.is_active == True, Staff.is_active == True)
    )
    return [
        {
            "staff_id": staff.id,
            "display_name": staff.display_name,
            "description": staff.description,
            "duration_minutes": link.duration_minutes,
            "price": link.price,
        }
        for link, staff in q.all()
    ]


@router.put("/services/{service_id}/staff")
async def service_staff_update(service_id: int, data: ServiceStaffBulk, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    if not await db.get(Service, service_id):
        raise HTTPException(404, "Service not found")
    await db.execute(delete(StaffService).where(StaffService.service_id == service_id))
    for link in data.links:
        db.add(StaffService(service_id=service_id, **link.model_dump()))
    await db.commit()
    return {"ok": True}


@router.get("/staff")
async def staff(active_only: bool = True, _: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Staff).order_by(Staff.display_name)
    if active_only:
        stmt = stmt.where(Staff.is_active == True)
    q = await db.execute(stmt)
    return q.scalars().all()


@router.post("/staff")
async def staff_create(data: StaffCreate, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    user_id = None
    if data.telegram_id:
        uq = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
        linked = uq.scalar_one_or_none()
        if not linked:
            linked = User(telegram_id=data.telegram_id, full_name=data.display_name, role="performer")
            db.add(linked)
            await db.flush()
        else:
            linked.role = "performer"
        user_id = linked.id

    row = Staff(
        user_id=user_id,
        display_name=data.display_name,
        description=data.description,
        can_manage_schedule=data.can_manage_schedule,
    )
    db.add(row)
    await db.flush()

    # New performers start with a predictable Mon-Fri 09:00-18:00 schedule.
    from datetime import time
    for weekday in range(7):
        db.add(WeeklySchedule(
            staff_id=row.id,
            weekday=weekday,
            start_time=time(9, 0) if weekday < 5 else None,
            end_time=time(18, 0) if weekday < 5 else None,
            is_working_day=weekday < 5,
        ))
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/staff/{staff_id}")
async def staff_patch(staff_id: int, data: StaffPatch, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(Staff, staff_id)
    if not row:
        raise HTTPException(404, "Performer not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/staff/eligible")
async def eligible_staff(
    service_ids: str = Query(...),
    _: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = list(dict.fromkeys(int(x) for x in service_ids.split(",") if x.strip()))
    if not ids:
        return []
    q = await db.execute(
        select(Staff)
        .join(StaffService, StaffService.staff_id == Staff.id)
        .where(
            Staff.is_active == True,
            StaffService.is_active == True,
            StaffService.service_id.in_(ids),
        )
        .group_by(Staff.id)
        .having(func.count(func.distinct(StaffService.service_id)) == len(ids))
        .order_by(Staff.display_name)
    )
    return q.scalars().all()


@router.get("/staff/{staff_id}/schedule")
async def get_schedule(staff_id: int, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and staff_row.user_id != user.id:
        raise HTTPException(403, "You can only view your own schedule")
    q = await db.execute(select(WeeklySchedule).where(WeeklySchedule.staff_id == staff_id).order_by(WeeklySchedule.weekday))
    return q.scalars().all()


@router.put("/staff/{staff_id}/schedule")
async def put_schedule(staff_id: int, data: WeeklyScheduleBulk, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and (staff_row.user_id != user.id or not staff_row.can_manage_schedule):
        raise HTTPException(403, "Schedule editing is disabled")
    existing_q = await db.execute(select(WeeklySchedule).where(WeeklySchedule.staff_id == staff_id))
    existing = {row.weekday: row for row in existing_q.scalars().all()}
    for item in data.rows:
        row = existing.get(item.weekday)
        if not row:
            row = WeeklySchedule(staff_id=staff_id, weekday=item.weekday)
            db.add(row)
        row.is_working_day = item.is_working_day
        row.start_time = item.start_time if item.is_working_day else None
        row.end_time = item.end_time if item.is_working_day else None
    await db.commit()
    return {"ok": True}


@router.get("/staff/{staff_id}/exceptions")
async def exceptions(staff_id: int, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and staff_row.user_id != user.id:
        raise HTTPException(403, "You can only view your own schedule exceptions")
    q = await db.execute(
        select(ScheduleException).where(ScheduleException.staff_id == staff_id).order_by(ScheduleException.target_date.desc()).limit(100)
    )
    return q.scalars().all()


@router.post("/staff/{staff_id}/exceptions")
async def exception_create(staff_id: int, data: ExceptionCreate, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and (staff_row.user_id != user.id or not staff_row.can_manage_schedule):
        raise HTTPException(403, "Schedule editing is disabled")
    row = ScheduleException(staff_id=staff_id, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/staff/{staff_id}/exceptions/{exception_id}")
async def exception_delete(staff_id: int, exception_id: int, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(ScheduleException, exception_id)
    staff_row = await db.get(Staff, staff_id)
    if not row or row.staff_id != staff_id or not staff_row:
        raise HTTPException(404, "Exception not found")
    if user.role == "performer" and (staff_row.user_id != user.id or not staff_row.can_manage_schedule):
        raise HTTPException(403, "Schedule editing is disabled")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/staff/{staff_id}/blocks")
async def blocks(staff_id: int, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and staff_row.user_id != user.id:
        raise HTTPException(403, "You can only view your own blocked intervals")
    q = await db.execute(
        select(BlockedInterval).where(BlockedInterval.staff_id == staff_id, BlockedInterval.end_at > datetime.utcnow()).order_by(BlockedInterval.start_at)
    )
    business = await get_business(db)
    return [
        {
            "id": x.id,
            "start_at": utc_naive_iso(x.start_at),
            "end_at": utc_naive_iso(x.end_at),
            "local_start": utc_naive_to_local(x.start_at, business.timezone).isoformat(),
            "local_end": utc_naive_to_local(x.end_at, business.timezone).isoformat(),
            "reason": x.reason,
        }
        for x in q.scalars().all()
    ]


@router.post("/staff/{staff_id}/blocks")
async def block_create(staff_id: int, data: BlockedIntervalCreate, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    staff_row = await db.get(Staff, staff_id)
    if not staff_row:
        raise HTTPException(404, "Performer not found")
    if user.role == "performer" and (staff_row.user_id != user.id or not staff_row.can_manage_schedule):
        raise HTTPException(403, "Schedule editing is disabled")
    business = await get_business(db)
    start = aware_to_utc_naive(data.start_at, business.timezone)
    end = aware_to_utc_naive(data.end_at, business.timezone)
    if end <= start:
        raise HTTPException(400, "End must be after start")
    row = BlockedInterval(staff_id=staff_id, start_at=start, end_at=end, reason=data.reason)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/staff/{staff_id}/blocks/{block_id}")
async def block_delete(staff_id: int, block_id: int, user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(BlockedInterval, block_id)
    staff_row = await db.get(Staff, staff_id)
    if not row or row.staff_id != staff_id or not staff_row:
        raise HTTPException(404, "Block not found")
    if user.role == "performer" and (staff_row.user_id != user.id or not staff_row.can_manage_schedule):
        raise HTTPException(403, "Schedule editing is disabled")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/availability")
async def availability(
    staff_id: int,
    service_ids: str,
    target_date: date,
    exclude_booking_id: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = [int(x) for x in service_ids.split(",") if x.strip()]
    if exclude_booking_id is not None:
        existing = await db.get(Booking, exclude_booking_id)
        if not existing or existing.staff_id != staff_id:
            raise HTTPException(404, "Запись не найдена")
        allowed = existing.client_user_id == user.id or user.role in {"owner", "admin"}
        if user.role == "performer":
            sq = await db.execute(select(Staff.id).where(Staff.user_id == user.id))
            allowed = sq.scalar_one_or_none() == staff_id
        if not allowed:
            raise HTTPException(403, "Нет доступа к этой записи")
    try:
        slots = await available_slots(db, staff_id, ids, target_date, exclude_booking_id=exclude_booking_id)
        return {"date": str(target_date), "slots": slots}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/bookings")
async def booking_create(data: BookingCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        booking = await create_booking(db, user, data.staff_id, data.service_ids, data.start_at, data.phone)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    business = await get_business(db)
    await notify_admins_new_booking(db, booking, business)
    return await booking_dict(db, booking, business)


@router.get("/my-bookings")
async def my_bookings(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    business = await get_business(db)
    q = await db.execute(
        select(Booking).where(Booking.client_user_id == user.id).order_by(Booking.start_at.desc()).limit(100)
    )
    return [await booking_dict(db, row, business) for row in q.scalars().all()]


@router.get("/bookings")
async def bookings(user: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    business = await get_business(db)
    stmt = select(Booking).order_by(Booking.start_at.desc()).limit(300)
    if user.role == "performer":
        sq = await db.execute(select(Staff.id).where(Staff.user_id == user.id))
        staff_id = sq.scalar_one_or_none()
        if not staff_id:
            return []
        stmt = stmt.where(Booking.staff_id == staff_id)
    q = await db.execute(stmt)
    return [await booking_dict(db, row, business) for row in q.scalars().all()]


@router.post("/bookings/{booking_id}/confirm")
async def booking_confirm(booking_id: int, actor: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status == "temporary_hold" and booking.hold_expires_at and booking.hold_expires_at <= datetime.utcnow():
        booking.status = "expired"
        await db.commit()
        raise HTTPException(409, "Temporary hold has already expired")
    if booking.status not in {"temporary_hold", "pending"}:
        raise HTTPException(409, "Booking cannot be confirmed")
    booking.status = "confirmed"
    booking.confirmed_at = datetime.utcnow()
    booking.hold_expires_at = None
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=actor.id, event_type="confirmed"))
    await db.commit()
    business = await get_business(db)
    await notify_client_status(db, booking, business, "✅ Запись подтверждена")
    return await booking_dict(db, booking, business)


@router.post("/bookings/{booking_id}/cancel")
async def booking_cancel(booking_id: int, actor: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status in {"completed", "cancelled_admin", "cancelled_client", "expired"}:
        raise HTTPException(409, "Booking is already closed")
    booking.status = "cancelled_admin"
    booking.hold_expires_at = None
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=actor.id, event_type="cancelled_admin"))
    await db.commit()
    business = await get_business(db)
    await notify_client_status(db, booking, business, "❌ Запись отменена администратором")
    return await booking_dict(db, booking, business)


@router.post("/bookings/{booking_id}/complete")
async def booking_complete(booking_id: int, actor: User = Depends(manager_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if actor.role == "performer":
        sq = await db.execute(select(Staff.id).where(Staff.user_id == actor.id))
        own_staff_id = sq.scalar_one_or_none()
        if own_staff_id != booking.staff_id:
            raise HTTPException(403, "You can only manage your own bookings")
    booking.status = "completed"
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=actor.id, event_type="completed"))
    await db.commit()
    business = await get_business(db)
    return await booking_dict(db, booking, business)

@router.post("/my-bookings/{booking_id}/cancel")
async def client_cancel(booking_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking or booking.client_user_id != user.id:
        raise HTTPException(404, "Booking not found")
    business = await get_business(db)
    if not business.allow_client_cancel:
        raise HTTPException(403, "Client cancellation is disabled")
    if booking.status not in {"temporary_hold", "pending", "confirmed"}:
        raise HTTPException(409, "Booking cannot be cancelled")
    if booking.status == "confirmed" and booking.start_at - datetime.utcnow() < timedelta(hours=business.cancel_before_hours):
        raise HTTPException(409, f"Cancellation is allowed no later than {business.cancel_before_hours} hours before the visit")
    booking.status = "cancelled_client"
    booking.hold_expires_at = None
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=user.id, event_type="cancelled_client"))
    await db.commit()
    await notify_admins_booking_event(db, booking, business, "❌ Клиент отменил запись")
    return await booking_dict(db, booking, business)


@router.post("/my-bookings/{booking_id}/reschedule")
async def client_reschedule(booking_id: int, data: BookingMove, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking or booking.client_user_id != user.id:
        raise HTTPException(404, "Запись не найдена")
    business = await get_business(db)
    if not business.allow_client_reschedule:
        raise HTTPException(403, "Перенос записи отключён администратором")
    if booking.status not in {"temporary_hold", "pending", "confirmed"}:
        raise HTTPException(409, "Эту запись уже нельзя перенести")
    if booking.status == "confirmed" and booking.start_at - datetime.utcnow() < timedelta(hours=business.reschedule_before_hours):
        raise HTTPException(409, f"Перенос доступен не позднее чем за {business.reschedule_before_hours} ч. до визита")

    iq = await db.execute(select(BookingItem.service_id).where(BookingItem.booking_id == booking.id).order_by(BookingItem.id))
    service_ids = list(iq.scalars().all())
    specs = await get_specs(db, booking.staff_id, service_ids)
    new_start = aware_to_utc_naive(data.start_at, business.timezone)
    new_end = new_start + timedelta(minutes=sum(x[1] for x in specs))
    if not await slot_is_free(db, booking.staff_id, new_start, new_end, exclude_booking_id=booking.id):
        raise HTTPException(409, "Это время уже занято. Выберите другой слот")

    from backend.booking import effective_work_window
    local_day = utc_naive_to_local(new_start, business.timezone).date()
    window = await effective_work_window(db, booking.staff_id, local_day, business.timezone)
    if not window or new_start < window[0] or new_end > window[1]:
        raise HTTPException(409, "Выбранное время находится вне графика исполнителя")
    if int((new_start - window[0]).total_seconds() // 60) % business.slot_step_minutes != 0:
        raise HTTPException(409, "Выбранное время не соответствует шагу записи")

    old = f"{booking.start_at.isoformat()}->{new_start.isoformat()}"
    booking.start_at = new_start
    booking.end_at = new_end
    if business.booking_confirmation_mode == "manual":
        booking.status = "temporary_hold"
        booking.hold_expires_at = datetime.utcnow() + timedelta(minutes=business.hold_minutes)
        booking.confirmed_at = None
    else:
        booking.status = "confirmed"
        booking.hold_expires_at = None
        booking.confirmed_at = datetime.utcnow()
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=user.id, event_type="rescheduled_client", payload=old))
    await db.commit()
    await notify_admins_booking_event(db, booking, business, "🔄 Клиент перенёс запись")
    return await booking_dict(db, booking, business)


@router.post("/bookings/manual")
async def manual_booking_create(data: AdminBookingCreate, actor: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    # A manual booking may belong to a person who has never opened the Telegram bot.
    # We keep a synthetic internal identity so the booking model stays uniform.
    synthetic_id = -int(datetime.utcnow().timestamp() * 1_000_000)
    client = User(telegram_id=synthetic_id, full_name=data.client_name, phone=data.phone, role="manual_client")
    db.add(client)
    await db.flush()
    try:
        booking = await create_booking(db, client, data.staff_id, data.service_ids, data.start_at, data.phone)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))
    booking.status = "confirmed"
    booking.hold_expires_at = None
    booking.confirmed_at = datetime.utcnow()
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=actor.id, event_type="manual_booking"))
    await db.commit()
    business = await get_business(db)
    return await booking_dict(db, booking, business)


@router.post("/bookings/{booking_id}/move")
async def admin_move_booking(booking_id: int, data: BookingMove, actor: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    business = await get_business(db)
    iq = await db.execute(select(BookingItem.service_id).where(BookingItem.booking_id == booking.id).order_by(BookingItem.id))
    service_ids = list(iq.scalars().all())
    specs = await get_specs(db, booking.staff_id, service_ids)
    new_start = aware_to_utc_naive(data.start_at, business.timezone)
    new_end = new_start + timedelta(minutes=sum(x[1] for x in specs))
    if not await slot_is_free(db, booking.staff_id, new_start, new_end, exclude_booking_id=booking.id):
        raise HTTPException(409, "Это время уже занято. Выберите другой слот")
    from backend.booking import effective_work_window
    local_day = utc_naive_to_local(new_start, business.timezone).date()
    window = await effective_work_window(db, booking.staff_id, local_day, business.timezone)
    if not window or new_start < window[0] or new_end > window[1]:
        raise HTTPException(409, "Выбранное время находится вне графика исполнителя")
    if int((new_start - window[0]).total_seconds() // 60) % business.slot_step_minutes != 0:
        raise HTTPException(409, "Выбранное время не соответствует шагу записи")
    old = f"{booking.start_at.isoformat()}->{new_start.isoformat()}"
    booking.start_at = new_start
    booking.end_at = new_end
    if booking.status in {"temporary_hold", "pending"}:
        booking.status = "confirmed"
        booking.confirmed_at = datetime.utcnow()
        booking.hold_expires_at = None
    db.add(BookingHistory(booking_id=booking.id, actor_user_id=actor.id, event_type="rescheduled_admin", payload=old))
    await db.commit()
    await notify_client_status(db, booking, business, "🔄 Запись перенесена администратором")
    return await booking_dict(db, booking, business)
