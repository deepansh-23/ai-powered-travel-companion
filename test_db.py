
import asyncio
import os
import ssl
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load settings from the project root .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Read database settings
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
name = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

# Check required settings
if not all([host, port, name, user, password]):
    raise ValueError(
        "Database settings are missing. Check DB_HOST, DB_PORT, "
        "DB_NAME, DB_USER and DB_PASSWORD in .env."
    )

# Build the database URL safely, including special characters in credentials
from sqlalchemy.engine import URL

database_url = URL.create(
    drivername="postgresql+asyncpg",
    username=user,
    password=password,
    host=host,
    port=int(port),
    database=name,
)

# Verify Aiven's certificate
ca_file = BASE_DIR / "ca.pem"

if not ca_file.is_file():
    raise FileNotFoundError(
        "ca.pem not found. Download Aiven's CA certificate "
        "and place it beside test_db.py."
    )

ssl_context = ssl.create_default_context(cafile=str(ca_file))

engine = create_async_engine(
    database_url,
    connect_args={"ssl": ssl_context},
    pool_pre_ping=True,
)


async def test_connection():
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))

            print("Database connection successful!")
            print("Test result:", result.scalar())

    except Exception as error:
        print("Database connection failed.")
        print("Error type:", type(error).__name__)
        print("Error details:", str(error).splitlines()[0])

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_connection())
