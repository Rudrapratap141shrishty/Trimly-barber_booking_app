from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    phone: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    model_config = ConfigDict(from_attributes=True)


class AppointmentRequest(BaseModel):
    barber_id: int
    service_id: int
    start_at: datetime


class AppointmentResponse(BaseModel):
    id: int
    barber_id: int
    service_id: int
    start_at: datetime
    end_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)