"""Async PostgreSQL (Aiven) connection.

Uses SQLAlchemy 2 + asyncpg and verifies Aiven's certificate with ca.pem.
If no database is configured the app still starts; only features that need
accounts return a clear 503 message.
"""

import logging
import ssl
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import HTTPException, status
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_init_error: Optional[str] = None
_tables_ready = False
_last_attempt = 0.0
_RETRY_AFTER_SECONDS = 5


def is_configured() -> bool:
    return bool(settings.DATABASE_URL or (settings.DB_HOST and settings.DB_NAME and settings.DB_USER))


def _build_url():
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    # URL.create escapes special characters in the password safely
    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=int(settings.DB_PORT),
        database=settings.DB_NAME,
    )


def _connect_args() -> dict:
    if settings.DATABASE_URL:  # tests / local overrides (e.g. sqlite+aiosqlite)
        return {}
    ca_file = Path(settings.DB_SSL_CA)
    if not ca_file.is_absolute():
        ca_file = settings.PROJECT_ROOT / ca_file
    if not ca_file.is_file():
        raise FileNotFoundError(
            f"Aiven CA certificate not found at {ca_file}. Download ca.pem from the Aiven console "
            "and place it in the project root (or set DB_SSL_CA)."
        )
    return {"ssl": ssl.create_default_context(cafile=str(ca_file))}


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        if not is_configured():
            raise RuntimeError("Database is not configured.")
        url = _build_url()
        kwargs = {"pool_pre_ping": True}
        if str(url).startswith("sqlite"):
            kwargs = {"poolclass": NullPool}  # tests / local file: no connection reuse across event loops
        else:
            kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
        _engine = create_async_engine(url, connect_args=_connect_args(), **kwargs)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def init_db() -> None:
    """Create tables if they do not exist. Never stops the app from starting."""
    global _init_error, _tables_ready, _last_attempt
    _last_attempt = time.monotonic()
    if not is_configured():
        _init_error = "Database is not configured (DB_HOST / DB_NAME / DB_USER missing in .env)."
        logger.warning(_init_error + " Accounts are disabled.")
        return
    try:
        from app.db_models import Base

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _init_error = None
        _tables_ready = True
        logger.info("Database ready (tables checked).")
    except Exception as exc:  # network, credentials, certificate...
        _init_error = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        logger.error("Database connection failed: %s", _init_error)


async def dispose_db() -> None:
    global _engine, _session_factory, _tables_ready
    if _engine is not None:
        await _engine.dispose()
    _engine, _session_factory, _tables_ready = None, None, False


def reset_for_tests() -> None:
    """Forget the engine and flags (tests switch to a fresh temporary database)."""
    global _engine, _session_factory, _init_error, _tables_ready, _last_attempt
    _engine, _session_factory, _init_error, _tables_ready, _last_attempt = None, None, None, False, 0.0


async def ensure_ready() -> None:
    """Make sure tables exist; retry a failed start-up connection (at most every few seconds)."""
    if _tables_ready:
        return
    if _init_error and (time.monotonic() - _last_attempt) < _RETRY_AFTER_SECONDS:
        return
    await init_db()


def db_status() -> dict:
    return {"configured": is_configured(), "ready": is_configured() and _init_error is None, "error": _init_error}


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one database session per request."""
    if is_configured():
        await ensure_ready()
    if not is_configured() or _init_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Accounts are temporarily unavailable (database not connected). Please try again later.",
        )
    get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
