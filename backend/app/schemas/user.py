from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid


# Request Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Response Schemas
class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    message: str
    user: UserResponse
