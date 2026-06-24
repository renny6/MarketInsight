import asyncio
from database import engine
from models import Base

async def create_tables():
    """
    Utility script to generate all tables in the PostgreSQL database.
    """
    print("Connecting to PostgreSQL to build schemas...")
    async with engine.begin() as conn:
        # Pushes the declarative Base models to the database
        await conn.run_sync(Base.metadata.create_all)
    print("Success! Watchlist, FinancialReport, and JobRun tables created.")

if __name__ == "__main__":
    # Run the async table creation
    asyncio.run(create_tables())