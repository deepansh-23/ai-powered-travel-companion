"""Username + password accounts, login sessions, lockout and recovery codes.

Security notes:
- Passwords and recovery codes are stored only as Argon2 hashes.
- The session cookie holds a random token; the database stores its SHA-256 only.
- Wrong-login messages are identical for "unknown user" and "wrong password",
  and an unknown user still costs one hash check (no timing leak).
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db_models import AccountDeletionRequest, AuthSession, Feedback, History, LoginAttempt, SavedSession, User, utcnow

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password-for-timing")

ENV_ADMIN_PROTECTED_MSG = "Cannot delete, disable, or demote the environment-configured recovery admin account."

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwertyui",
    "qwerty123", "iloveyou", "admin123", "welcome1", "letmein1", "abc12345", "11111111",
}
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


class AuthError(Exception):
    """Base class: message is safe to show to the user."""

    status_code = 400


class ValidationFailed(AuthError):
    status_code = 422


class InvalidCredentials(AuthError):
    status_code = 401


class LockedOut(AuthError):
    status_code = 429


class UsernameTaken(AuthError):
    status_code = 409


class EnvAdminProtected(AuthError):
    status_code = 403


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password or "")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def is_env_admin(user_or_username) -> bool:
    """Return True if the given User or username matches the configured ADMIN_USERNAME."""
    configured = (settings.ADMIN_USERNAME or "").strip().lower()[:30]
    if not configured:
        return False
    if isinstance(user_or_username, str):
        candidate = user_or_username.strip().lower()[:30]
    else:
        candidate = (
            getattr(user_or_username, "username_lower", None)
            or getattr(user_or_username, "username", "")
            or ""
        ).strip().lower()[:30]
    return bool(candidate) and candidate == configured


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------- validation
def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise ValidationFailed("Username must be 3 to 30 characters: letters, numbers and underscore only.")
    return username


def validate_password(password: str, username: str = "") -> str:
    password = password or ""
    if len(password) < 8:
        raise ValidationFailed("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValidationFailed("Password must be at most 128 characters.")
    if password.lower() in _COMMON_PASSWORDS:
        raise ValidationFailed("That password is too common. Please choose a less predictable one.")
    if username and username.lower() in password.lower():
        raise ValidationFailed("Password must not contain your username.")
    return password


def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _normalise_recovery_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


# ---------------------------------------------------------------- lockout
async def _recent_failures(db: AsyncSession, username_lower: str, ip: str) -> Tuple[int, int, Optional[datetime]]:
    since = utcnow() - timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)
    user_q = select(func.count(), func.min(LoginAttempt.attempted_at)).where(
        LoginAttempt.username_lower == username_lower,
        LoginAttempt.success.is_(False),
        LoginAttempt.attempted_at >= since,
    )
    ip_q = select(func.count()).where(
        LoginAttempt.ip == ip, LoginAttempt.success.is_(False), LoginAttempt.attempted_at >= since
    )
    user_count, first = (await db.execute(user_q)).one()
    ip_count = (await db.execute(ip_q)).scalar_one()
    return int(user_count or 0), int(ip_count or 0), first


async def _check_lockout(db: AsyncSession, username_lower: str, ip: str) -> None:
    user_fail, ip_fail, first = await _recent_failures(db, username_lower, ip)
    limit = settings.AUTH_MAX_FAILED_ATTEMPTS
    if user_fail >= limit or ip_fail >= limit * 3:
        wait = settings.AUTH_LOCKOUT_MINUTES
        if first is not None:
            elapsed = (utcnow() - _as_utc(first)).total_seconds() / 60
            wait = max(1, int(settings.AUTH_LOCKOUT_MINUTES - elapsed + 0.999))
        raise LockedOut(f"Too many failed attempts. Please try again in about {wait} minute(s).")


async def _record_attempt(db: AsyncSession, username_lower: str, ip: str, success: bool) -> None:
    db.add(LoginAttempt(username_lower=username_lower[:30], ip=(ip or "unknown")[:64], success=success))
    await db.commit()


# ---------------------------------------------------------------- accounts
async def register(db: AsyncSession, username: str, password: str) -> Tuple[User, str]:
    username = validate_username(username)
    validate_password(password, username)
    recovery = _new_recovery_code()
    user = User(
        username=username,
        username_lower=username.lower(),
        password_hash=_hasher.hash(password),
        recovery_code_hash=_hasher.hash(_normalise_recovery_code(recovery)),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise UsernameTaken("That username is already taken. Please choose another.")
    return user, recovery


async def authenticate(db: AsyncSession, username: str, password: str, ip: str) -> User:
    username_lower = (username or "").strip().lower()[:30]
    await _check_lockout(db, username_lower, ip)

    user = (await db.execute(select(User).where(User.username_lower == username_lower))).scalar_one_or_none()
    ok = False
    if user is not None and user.is_active:
        try:
            ok = _hasher.verify(user.password_hash, password or "")
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            ok = False
    else:
        try:  # same cost as a real check, so response time does not reveal unknown usernames
            _hasher.verify(_DUMMY_HASH, password or "")
        except Exception:
            pass

    if not ok or user is None:
        await _record_attempt(db, username_lower, ip, False)
        raise InvalidCredentials("Incorrect username or password.")

    await db.execute(
        delete(LoginAttempt).where(LoginAttempt.username_lower == username_lower, LoginAttempt.success.is_(False))
    )
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
    user.last_login_at = utcnow()
    await db.commit()
    return user


async def recover_account(db: AsyncSession, username: str, recovery_code: str, new_password: str, ip: str) -> Tuple[User, str]:
    """Reset the password with the one-time recovery code; returns the user and a NEW code."""
    username_lower = (username or "").strip().lower()[:30]
    await _check_lockout(db, username_lower, ip)
    user = (await db.execute(select(User).where(User.username_lower == username_lower))).scalar_one_or_none()
    good = False
    if user is not None and user.recovery_code_hash:
        try:
            good = _hasher.verify(user.recovery_code_hash, _normalise_recovery_code(recovery_code))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            good = False
    else:
        try:
            _hasher.verify(_DUMMY_HASH, "x")
        except Exception:
            pass
    if not good or user is None:
        await _record_attempt(db, username_lower, ip, False)
        raise InvalidCredentials("Username or recovery code is incorrect.")

    validate_password(new_password, user.username)
    new_code = _new_recovery_code()
    user.password_hash = _hasher.hash(new_password)
    user.recovery_code_hash = _hasher.hash(_normalise_recovery_code(new_code))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))  # log out everywhere
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_lower == username_lower))
    await db.commit()
    return user, new_code


async def change_password(db: AsyncSession, user: User, current: str, new: str) -> None:
    try:
        if not _hasher.verify(user.password_hash, current or ""):
            raise InvalidCredentials("Current password is incorrect.")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        raise InvalidCredentials("Current password is incorrect.")
    validate_password(new, user.username)
    user.password_hash = _hasher.hash(new)
    await db.commit()


async def delete_account(db: AsyncSession, user: User, password: str) -> None:
    """Permanently delete the account after re-checking the password.

    Removes the profile, login sessions, history and saved sessions. Reviews stay on the
    Reviews page but are detached from the account (they become anonymous).
    """
    if is_env_admin(user):
        raise EnvAdminProtected(ENV_ADMIN_PROTECTED_MSG)

    try:
        ok = _hasher.verify(user.password_hash, password or "")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        ok = False
    if not ok:
        raise InvalidCredentials("Password is incorrect. Your account was not deleted.")

    uid, uname = user.id, user.username_lower
    await db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == uid))
    await db.execute(update(Feedback).where(Feedback.user_id == uid).values(user_id=None))
    await db.execute(delete(History).where(History.user_id == uid))
    await db.execute(delete(SavedSession).where(SavedSession.user_id == uid))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_lower == uname))
    await db.execute(delete(User).where(User.id == uid))
    await db.commit()


# ---------------------------------------------------------------- sessions
async def create_session(db: AsyncSession, user: User, user_agent: Optional[str] = None) -> str:
    now = utcnow()
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at < now))
    raw = secrets.token_urlsafe(32)
    db.add(AuthSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(days=settings.AUTH_SESSION_DAYS),
        user_agent=(user_agent or "")[:200] or None,
    ))
    await db.commit()
    return raw


async def get_user_for_token(db: AsyncSession, raw: Optional[str]) -> Optional[User]:
    if not raw:
        return None
    row = (await db.execute(
        select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.token_hash == hash_token(raw))
    )).first()
    if row is None:
        return None
    session, user = row
    now = utcnow()
    if _as_utc(session.expires_at) <= now or not user.is_active:
        return None
    if (now - _as_utc(session.last_seen_at)).total_seconds() > 300:  # avoid a write on every request
        session.last_seen_at = now
        await db.commit()
    return user


async def end_session(db: AsyncSession, raw: Optional[str]) -> None:
    if raw:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(raw)))
        await db.commit()


# ---------------------------------------------------------------- env recovery admin
async def _sync_env_admin(db: AsyncSession, username: str, password: str) -> None:
    username_lower = username.lower()[:30]
    user = (await db.execute(select(User).where(User.username_lower == username_lower))).scalar_one_or_none()

    if user is None:
        user_kwargs = {
            "username": username,
            "username_lower": username_lower,
            "password_hash": hash_password(password),
            "recovery_code_hash": None,
            "is_active": True,
            "is_admin": True,
        }
        if hasattr(User, "email"):
            user_kwargs["email"] = settings.ADMIN_EMAIL or f"{username_lower}@admin.local"
        db.add(User(**user_kwargs))
        try:
            await db.commit()
            logger.info("Created environment recovery admin account '%s'.", username)
            return
        except IntegrityError:
            await db.rollback()
            # Concurrent worker startup may have just created the row; re-fetch and sync
            user = (await db.execute(select(User).where(User.username_lower == username_lower))).scalar_one_or_none()
            if user is None:
                raise

    changed = False
    if user.username != username:
        user.username = username
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if not getattr(user, "is_admin", False):
        user.is_admin = True
        changed = True
    if hasattr(User, "email") and settings.ADMIN_EMAIL and getattr(user, "email", None) != settings.ADMIN_EMAIL:
        setattr(user, "email", settings.ADMIN_EMAIL)
        changed = True
    if not verify_password(user.password_hash, password) or _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        changed = True

    cleared_lockout = await db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.username_lower == username_lower,
            LoginAttempt.success.is_(False),
        )
    )
    cleared_deletion = await db.execute(
        delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id)
    )

    if changed or (cleared_lockout.rowcount or 0) > 0 or (cleared_deletion.rowcount or 0) > 0:
        await db.commit()
        logger.info("Synced environment recovery admin account '%s'.", username)


async def ensure_env_admin(db: Optional[AsyncSession] = None) -> None:
    """Idempotently create or restore the .env-configured recovery admin account on startup.

    Exits quietly if ADMIN_USERNAME or ADMIN_PASSWORD is not configured or the database is not ready.
    Never logs or exposes ADMIN_PASSWORD.
    """
    username = (settings.ADMIN_USERNAME or "").strip()
    password = settings.ADMIN_PASSWORD or ""
    if not username or not password:
        return

    try:
        username = validate_username(username)
    except ValidationFailed as exc:
        logger.warning("Skipping environment recovery admin bootstrap for '%s': %s", username, exc)
        return

    try:
        if db is not None:
            await _sync_env_admin(db, username, password)
            return

        from app.db import db_status, session_scope
        if not db_status().get("ready"):
            return
        async with session_scope() as session:
            await _sync_env_admin(session, username, password)
    except Exception as exc:
        # Log only the exception type so credentials/parameters can never leak into logs
        logger.error("Failed to ensure environment recovery admin '%s': %s", username, type(exc).__name__)
