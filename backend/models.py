from datetime import datetime,date,time
from sqlalchemy import String,Integer,Boolean,DateTime,Date,Time,ForeignKey,Text,UniqueConstraint,Float
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column
class Base(DeclarativeBase): pass
class Business(Base):
    __tablename__='businesses'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),default='EasyBook')
    timezone:Mapped[str]=mapped_column(String(64),default='Europe/Moscow')
    currency:Mapped[str|None]=mapped_column(String(16),nullable=True)
    booking_confirmation_mode:Mapped[str]=mapped_column(String(16),default='manual')
    hold_minutes:Mapped[int]=mapped_column(Integer,default=15)
    slot_step_minutes:Mapped[int]=mapped_column(Integer,default=30)
    allow_client_cancel:Mapped[bool]=mapped_column(Boolean,default=True)
    cancel_before_hours:Mapped[int]=mapped_column(Integer,default=24)
    allow_client_reschedule:Mapped[bool]=mapped_column(Boolean,default=True)
    reschedule_before_hours:Mapped[int]=mapped_column(Integer,default=24)
    booking_horizon_days:Mapped[int]=mapped_column(Integer,default=60)
    is_onboarded:Mapped[bool]=mapped_column(Boolean,default=False)
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    telegram_id:Mapped[int]=mapped_column(Integer,unique=True,index=True)
    full_name:Mapped[str]=mapped_column(String(160),default='')
    phone:Mapped[str|None]=mapped_column(String(40),nullable=True)
    role:Mapped[str]=mapped_column(String(20),default='client')
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Staff(Base):
    __tablename__='staff'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    display_name:Mapped[str]=mapped_column(String(120))
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    can_manage_schedule:Mapped[bool]=mapped_column(Boolean,default=False)
class Service(Base):
    __tablename__='services'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120))
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    default_duration_minutes:Mapped[int]=mapped_column(Integer,default=60)
    default_price:Mapped[float|None]=mapped_column(Float,nullable=True)
class StaffService(Base):
    __tablename__='staff_services'; __table_args__=(UniqueConstraint('staff_id','service_id'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    staff_id:Mapped[int]=mapped_column(ForeignKey('staff.id'))
    service_id:Mapped[int]=mapped_column(ForeignKey('services.id'))
    duration_minutes:Mapped[int|None]=mapped_column(Integer,nullable=True)
    price:Mapped[float|None]=mapped_column(Float,nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
class WeeklySchedule(Base):
    __tablename__='weekly_schedules'; __table_args__=(UniqueConstraint('staff_id','weekday'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    staff_id:Mapped[int]=mapped_column(ForeignKey('staff.id'))
    weekday:Mapped[int]=mapped_column(Integer)
    start_time:Mapped[time|None]=mapped_column(Time,nullable=True)
    end_time:Mapped[time|None]=mapped_column(Time,nullable=True)
    is_working_day:Mapped[bool]=mapped_column(Boolean,default=True)
class ScheduleException(Base):
    __tablename__='schedule_exceptions'
    id:Mapped[int]=mapped_column(primary_key=True)
    staff_id:Mapped[int]=mapped_column(ForeignKey('staff.id'))
    target_date:Mapped[date]=mapped_column(Date)
    is_closed:Mapped[bool]=mapped_column(Boolean,default=False)
    start_time:Mapped[time|None]=mapped_column(Time,nullable=True)
    end_time:Mapped[time|None]=mapped_column(Time,nullable=True)
class BlockedInterval(Base):
    __tablename__='blocked_intervals'
    id:Mapped[int]=mapped_column(primary_key=True)
    staff_id:Mapped[int]=mapped_column(ForeignKey('staff.id'))
    start_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    end_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    reason:Mapped[str|None]=mapped_column(String(160),nullable=True)
class Booking(Base):
    __tablename__='bookings'
    id:Mapped[int]=mapped_column(primary_key=True)
    client_user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    staff_id:Mapped[int]=mapped_column(ForeignKey('staff.id'))
    start_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    end_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    status:Mapped[str]=mapped_column(String(32),default='temporary_hold')
    hold_expires_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    confirmed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
class BookingItem(Base):
    __tablename__='booking_items'
    id:Mapped[int]=mapped_column(primary_key=True)
    booking_id:Mapped[int]=mapped_column(ForeignKey('bookings.id'))
    service_id:Mapped[int]=mapped_column(ForeignKey('services.id'))
    duration_minutes:Mapped[int]=mapped_column(Integer)
    price:Mapped[float|None]=mapped_column(Float,nullable=True)
class BookingHistory(Base):
    __tablename__='booking_history'
    id:Mapped[int]=mapped_column(primary_key=True)
    booking_id:Mapped[int]=mapped_column(ForeignKey('bookings.id'))
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    event_type:Mapped[str]=mapped_column(String(64))
    payload:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Blacklist(Base):
    __tablename__='blacklist'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    reason:Mapped[str|None]=mapped_column(Text,nullable=True)
class WaitingList(Base):
    __tablename__='waiting_list'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    staff_id:Mapped[int|None]=mapped_column(ForeignKey('staff.id'),nullable=True)
    service_id:Mapped[int]=mapped_column(ForeignKey('services.id'))
    target_date:Mapped[date]=mapped_column(Date)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
