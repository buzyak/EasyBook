import asyncio
from datetime import datetime, timedelta, date
from sqlalchemy import select, or_, delete

from backend.models import (
    Booking, BookingItem, BookingHistory, Service, StaffService, Blacklist,
    User, Business, WeeklySchedule, ScheduleException, BlockedInterval, Staff,
)
from backend.timeutils import local_dt_to_utc_naive, aware_to_utc_naive, utc_naive_iso

ACTIVE_STATUSES = {"temporary_hold", "pending", "confirmed"}
_booking_lock = asyncio.Lock()


async def get_business(db) -> Business:
    q = await db.execute(select(Business).limit(1))
    business = q.scalar_one_or_none()
    if not business:
        business = Business(timezone="Europe/Moscow")
        db.add(business)
        await db.flush()
    return business


async def get_specs(db, staff_id: int, service_ids: list[int]):
    service_ids = list(dict.fromkeys(service_ids))
    if not service_ids:
        raise ValueError("Choose at least one service")
    out = []
    for sid in service_ids:
        q = await db.execute(
            select(StaffService).where(
                StaffService.staff_id == staff_id,
                StaffService.service_id == sid,
                StaffService.is_active == True,
            )
        )
        ss = q.scalar_one_or_none()
        if not ss:
            raise ValueError("Selected performer cannot provide all chosen services")
        q = await db.execute(select(Service).where(Service.id == sid, Service.is_active == True))
        service = q.scalar_one_or_none()
        if not service:
            raise ValueError("Service is unavailable")
        out.append((
            service,
            ss.duration_minutes or service.default_duration_minutes,
            ss.price if ss.price is not None else service.default_price,
        ))
    return out


async def effective_work_window(db, staff_id: int, target_date: date, timezone_name: str):
    eq = await db.execute(
        select(ScheduleException).where(
            ScheduleException.staff_id == staff_id,
            ScheduleException.target_date == target_date,
        ).order_by(ScheduleException.id.desc())
    )
    exception = eq.scalars().first()
    if exception:
        if exception.is_closed:
            return None
        if exception.start_time and exception.end_time:
            return (
                local_dt_to_utc_naive(target_date, exception.start_time, timezone_name),
                local_dt_to_utc_naive(target_date, exception.end_time, timezone_name),
            )

    sq = await db.execute(
        select(WeeklySchedule).where(
            WeeklySchedule.staff_id == staff_id,
            WeeklySchedule.weekday == target_date.weekday(),
        )
    )
    row = sq.scalar_one_or_none()
    if not row or not row.is_working_day or not row.start_time or not row.end_time:
        return None
    return (
        local_dt_to_utc_naive(target_date, row.start_time, timezone_name),
        local_dt_to_utc_naive(target_date, row.end_time, timezone_name),
    )


async def slot_is_free(db, staff_id: int, start_at: datetime, end_at: datetime, exclude_booking_id: int | None = None) -> bool:
    now = datetime.utcnow()
    stmt = select(Booking.id).where(
            Booking.staff_id == staff_id,
            Booking.status.in_(ACTIVE_STATUSES),
            Booking.start_at < end_at,
            Booking.end_at > start_at,
            or_(Booking.status != "temporary_hold", Booking.hold_expires_at > now),
        )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    bq = await db.execute(stmt.limit(1))
    if bq.scalar_one_or_none() is not None:
        return False

    iq = await db.execute(
        select(BlockedInterval.id).where(
            BlockedInterval.staff_id == staff_id,
            BlockedInterval.start_at < end_at,
            BlockedInterval.end_at > start_at,
        ).limit(1)
    )
    return iq.scalar_one_or_none() is None


async def available_slots(db, staff_id: int, service_ids: list[int], target_date: date, exclude_booking_id: int | None = None):
    business = await get_business(db)
    specs = await get_specs(db, staff_id, service_ids)
    total_minutes = sum(item[1] for item in specs)
    work = await effective_work_window(db, staff_id, target_date, business.timezone)
    if not work:
        return []

    start_work, end_work = work
    step = timedelta(minutes=business.slot_step_minutes)
    duration = timedelta(minutes=total_minutes)
    now = datetime.utcnow()
    cursor = start_work
    slots = []
    while cursor + duration <= end_work:
        if cursor > now and await slot_is_free(db, staff_id, cursor, cursor + duration, exclude_booking_id=exclude_booking_id):
            slots.append({
                "start_at": utc_naive_iso(cursor),
                "end_at": utc_naive_iso(cursor + duration),
            })
        cursor += step
    return slots


async def create_booking(db, user: User, staff_id: int, service_ids: list[int], start_at: datetime, phone: str | None = None):
    async with _booking_lock:
        if phone:
            user.phone = phone.strip()
        if not user.phone:
            raise ValueError("Phone number is required")

        q = await db.execute(select(Blacklist).where(Blacklist.user_id == user.id))
        if q.scalar_one_or_none():
            raise ValueError("Online booking is unavailable for this account")

        staff_q = await db.execute(select(Staff).where(Staff.id == staff_id, Staff.is_active == True))
        if not staff_q.scalar_one_or_none():
            raise ValueError("Performer is unavailable")

        business = await get_business(db)
        start_at = aware_to_utc_naive(start_at, business.timezone)
        specs = await get_specs(db, staff_id, service_ids)
        end_at = start_at + timedelta(minutes=sum(x[1] for x in specs))

        if not await slot_is_free(db, staff_id, start_at, end_at):
            raise ValueError("Selected time is no longer available")

        # Validate that the slot is inside the configured work window.
        from backend.timeutils import utc_naive_to_local
        local_day = utc_naive_to_local(start_at, business.timezone).date()
        window = await effective_work_window(db, staff_id, local_day, business.timezone)
        if not window or start_at < window[0] or end_at > window[1]:
            raise ValueError("Selected time is outside the performer's schedule")
        offset_minutes = int((start_at - window[0]).total_seconds() // 60)
        if offset_minutes % business.slot_step_minutes != 0:
            raise ValueError("Selected time does not match the configured booking step")

        now = datetime.utcnow()
        auto = business.booking_confirmation_mode == "auto"
        booking = Booking(
            client_user_id=user.id,
            staff_id=staff_id,
            start_at=start_at,
            end_at=end_at,
            status="confirmed" if auto else "temporary_hold",
            hold_expires_at=None if auto else now + timedelta(minutes=business.hold_minutes),
            confirmed_at=now if auto else None,
        )
        db.add(booking)
        await db.flush()

        for service, duration, price in specs:
            db.add(BookingItem(
                booking_id=booking.id,
                service_id=service.id,
                duration_minutes=duration,
                price=price,
            ))
        db.add(BookingHistory(
            booking_id=booking.id,
            actor_user_id=user.id,
            event_type="created",
            payload=f"status={booking.status}",
        ))
        await db.commit()
        await db.refresh(booking)
        return booking


async def cleanup_expired_holds(db):
    now = datetime.utcnow()
    q = await db.execute(
        select(Booking).where(
            Booking.status == "temporary_hold",
            Booking.hold_expires_at <= now,
        )
    )
    changed = 0
    for booking in q.scalars().all():
        booking.status = "expired"
        db.add(BookingHistory(
            booking_id=booking.id,
            actor_user_id=None,
            event_type="hold_expired",
        ))
        changed += 1
    if changed:
        await db.commit()
    return changed
