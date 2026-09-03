from datetime import datetime, time, date
from pydantic import BaseModel, Field

class BusinessSetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = "Europe/Moscow"
    currency: str | None = None

class BusinessSettingsPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None
    currency: str | None = None
    booking_confirmation_mode: str | None = None
    hold_minutes: int | None = Field(default=None, ge=1, le=120)
    slot_step_minutes: int | None = Field(default=None, ge=5, le=240)
    allow_client_cancel: bool | None = None
    cancel_before_hours: int | None = Field(default=None, ge=0, le=720)
    allow_client_reschedule: bool | None = None
    reschedule_before_hours: int | None = Field(default=None, ge=0, le=720)
    booking_horizon_days: int | None = Field(default=None, ge=1, le=365)

class StaffCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    telegram_id: int | None = None
    can_manage_schedule: bool = False

class StaffPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None
    can_manage_schedule: bool | None = None

class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    default_duration_minutes: int = Field(default=60, ge=5, le=1440)
    default_price: float | None = None
    staff_ids: list[int] = Field(default_factory=list)

class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    default_duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    default_price: float | None = None
    is_active: bool | None = None

class StaffServiceUpdate(BaseModel):
    staff_id: int
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    price: float | None = None
    is_active: bool = True

class ServiceStaffBulk(BaseModel):
    links: list[StaffServiceUpdate]

class WeeklyScheduleRow(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    is_working_day: bool = True

class WeeklyScheduleBulk(BaseModel):
    rows: list[WeeklyScheduleRow]

class ExceptionCreate(BaseModel):
    target_date: date
    is_closed: bool = True
    start_time: time | None = None
    end_time: time | None = None

class BlockedIntervalCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str | None = None

class BookingCreate(BaseModel):
    staff_id: int
    service_ids: list[int] = Field(min_length=1)
    start_at: datetime
    phone: str | None = Field(default=None, max_length=40)

class AdminBookingCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=3, max_length=40)
    staff_id: int
    service_ids: list[int] = Field(min_length=1)
    start_at: datetime

class BookingMove(BaseModel):
    start_at: datetime
