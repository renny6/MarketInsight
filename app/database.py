import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from the .env file.")

# --- Architecture Mandate: Connection Pool Optimization ---
# Configured specifically to prevent the "9:00 AM Crash" when APScheduler triggers
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Base permanent connection pool size
    max_overflow=10,       # Maximum transient bursting connections
    pool_timeout=30,       # Absolute timeout limit before discarding execution
    pool_recycle=1800,     # Recycle connections after 30 minutes to clean leaks
    echo=False             # Set to True if you want to see SQL queries in terminal
)

# Create a customized session factory
AsyncSessionLocal = sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Dependency injection for FastAPI routes later
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session