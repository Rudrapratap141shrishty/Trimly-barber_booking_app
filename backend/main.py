from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, engine, get_db, settings
from models import User, Barber, Service, Appointment
from schemas import (
    RegisterRequest,
    LoginRequest,
    UserResponse,
    AppointmentRequest
)
from security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token
)


security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    db = next(get_db())

    try:
        if db.scalar(select(Barber.id).limit(1)) is None:
            db.add_all([
                Barber(
                    name="Arjun Sharma",
                    role="Master Barber",
                    price_from=199
                ),
                Barber(
                    name="Rahul Verma",
                    role="Senior Stylist",
                    price_from=249
                ),
                Barber(
                    name="Kabir Singh",
                    role="Style Specialist",
                    price_from=299
                )
            ])

        if db.scalar(select(Service.id).limit(1)) is None:
            db.add_all([
                Service(
                    name="Classic Haircut",
                    duration_minutes=30,
                    price=199
                ),
                Service(
                    name="Haircut + Beard",
                    duration_minutes=45,
                    price=349
                ),
                Service(
                    name="Beard Styling",
                    duration_minutes=20,
                    price=149
                ),
                Service(
                    name="Premium Grooming",
                    duration_minutes=60,
                    price=599
                )
            ])

        db.commit()

    finally:
        db.close()

    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.frontend_origin.split(",")
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"]
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token"
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user


@app.get("/")
def root():
    return {
        "message": "Welcome to Trimly Barber Booking API",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    existing_user = db.scalar(
        select(User).where(User.email == data.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered"
        )

    user = User(
        name=data.name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role="customer"
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email is already registered"
        )

    return {
        "message": "Registration successful",
        "user_id": user.id
    }


@app.post("/api/auth/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.scalar(
        select(User).where(User.email == data.email)
    )

    if not user or not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }


@app.get("/api/auth/me", response_model=UserResponse)
def current_user(
    user: User = Depends(get_current_user)
):
    return user


@app.get("/api/barbers")
def list_barbers(db: Session = Depends(get_db)):
    barbers = db.scalars(
        select(Barber).where(Barber.is_active.is_(True))
    ).all()

    return [
        {
            "id": barber.id,
            "name": barber.name,
            "role": barber.role,
            "rating": barber.rating,
            "price_from": barber.price_from
        }
        for barber in barbers
    ]


@app.get("/api/services")
def list_services(db: Session = Depends(get_db)):
    services = db.scalars(
        select(Service).where(Service.is_active.is_(True))
    ).all()

    return [
        {
            "id": service.id,
            "name": service.name,
            "duration_minutes": service.duration_minutes,
            "price": service.price
        }
        for service in services
    ]


@app.get("/api/appointments/slots")
def appointment_slots(
    barber_id: int,
    service_id: int,
    date: str,
    db: Session = Depends(get_db)
):
    try:
        selected_date = datetime.strptime(date, "%Y-%m-%d").date()

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Date must use YYYY-MM-DD format"
        )

    barber = db.get(Barber, barber_id)
    service = db.get(Service, service_id)

    if not barber or not barber.is_active:
        raise HTTPException(status_code=404, detail="Barber not found")

    if not service or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")

    day_start = datetime.combine(
        selected_date,
        datetime.min.time()
    )

    day_end = day_start + timedelta(days=1)

    appointments = db.scalars(
        select(Appointment).where(
            Appointment.barber_id == barber_id,
            Appointment.status == "confirmed",
            Appointment.start_at < day_end,
            Appointment.end_at > day_start
        )
    ).all()

    busy = [
        (appointment.start_at, appointment.end_at)
        for appointment in appointments
    ]

    now = datetime.now()

    slots = []

    for hour in range(10, 19):
        start = datetime.combine(
            selected_date,
            datetime.min.time()
        ).replace(hour=hour)

        end = start + timedelta(minutes=service.duration_minutes)

        if selected_date == now.date() and start <= now:
            continue

        if end.hour > 19 or (end.hour == 19 and end.minute > 0):
            continue

        overlaps = any(
            start < busy_end and end > busy_start
            for busy_start, busy_end in busy
        )

        if not overlaps:
            slots.append({
                "start_at": start.isoformat(),
                "label": start.strftime("%I:%M %p")
            })

    return slots


@app.post("/api/appointments", status_code=201)
def create_appointment(
    data: AppointmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    barber = db.get(Barber, data.barber_id)
    service = db.get(Service, data.service_id)

    if not barber or not barber.is_active:
        raise HTTPException(status_code=404, detail="Barber not found")

    if not service or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found")

    start = data.start_at

    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc).replace(tzinfo=None)

    now = datetime.utcnow()

    if start <= now:
        raise HTTPException(
            status_code=400,
            detail="Appointment must be in the future"
        )

    if start.second != 0 or start.microsecond != 0:
        raise HTTPException(
            status_code=400,
            detail="Appointment must start on a minute boundary"
        )

    if start.minute != 0 or not 10 <= start.hour < 19:
        raise HTTPException(
            status_code=400,
            detail="Choose a valid hourly slot between 10 AM and 6 PM"
        )

    end = start + timedelta(minutes=service.duration_minutes)

    if end.hour > 19 or (end.hour == 19 and end.minute > 0):
        raise HTTPException(
            status_code=400,
            detail="Appointment must finish by 7 PM"
        )

    conflict = db.scalar(
        select(Appointment.id).where(
            Appointment.barber_id == barber.id,
            Appointment.status == "confirmed",
            Appointment.start_at < end,
            Appointment.end_at > start
        ).limit(1)
    )

    if conflict:
        raise HTTPException(
            status_code=409,
            detail="This appointment slot is no longer available"
        )

    appointment = Appointment(
        customer_id=user.id,
        barber_id=barber.id,
        service_id=service.id,
        start_at=start,
        end_at=end,
        status="confirmed"
    )

    db.add(appointment)

    try:
        db.commit()
        db.refresh(appointment)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Appointment conflicts with an existing booking"
        )

    return {
        "id": appointment.id,
        "barber_id": appointment.barber_id,
        "service_id": appointment.service_id,
        "start_at": appointment.start_at,
        "end_at": appointment.end_at,
        "status": appointment.status
    }


@app.get("/api/appointments")
def my_appointments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appointments = db.scalars(
        select(Appointment)
        .where(Appointment.customer_id == user.id)
        .order_by(Appointment.start_at.desc())
    ).all()

    return [
        {
            "id": item.id,
            "barber_id": item.barber_id,
            "service_id": item.service_id,
            "start_at": item.start_at,
            "end_at": item.end_at,
            "status": item.status
        }
        for item in appointments
    ]


@app.patch("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    appointment = db.get(Appointment, appointment_id)

    if not appointment or appointment.customer_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    if appointment.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Appointment cannot be cancelled"
        )

    appointment.status = "cancelled"
    db.commit()

    return {
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment.id
    }