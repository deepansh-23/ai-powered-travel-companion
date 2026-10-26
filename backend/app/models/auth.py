"""Request/response models for accounts. Detailed rules live in auth_service."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field("", max_length=100)
    password: str = Field("", max_length=300)
    captcha_token: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field("", max_length=100)
    password: str = Field("", max_length=300)
    captcha_token: Optional[str] = None


class RecoverRequest(BaseModel):
    username: str = Field("", max_length=100)
    recovery_code: str = Field("", max_length=100)
    new_password: str = Field("", max_length=300)
    captcha_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field("", max_length=300)
    new_password: str = Field("", max_length=300)


class DeleteAccountRequest(BaseModel):
    password: str = Field("", max_length=300)


class DeletionRequestBody(BaseModel):
    reason: str = Field("", max_length=300)


class GuestStartRequest(BaseModel):
    captcha_token: Optional[str] = None


class UserPublic(BaseModel):
    id: str
    username: str
    is_admin: bool = False
    created_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    user: UserPublic
    recovery_code: Optional[str] = None  # shown ONCE (register / recover)


class MeResponse(BaseModel):
    authenticated: bool
    user: Optional[UserPublic] = None
    accounts_available: bool = True
    guest: bool = False
