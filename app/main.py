import os
import time
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pytz import timezone as pytz_timezone

from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# Import database utilities and models
from app.database import AsyncSessionLocal, get_db
from app.models import Watchlist, FinancialReport, JobRun

# Import the LangGraph compiler and ReportState
from app.agent import app_graph, ReportState

print("Backend logic started successfully!")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("marketinsight.api")

# --- Timezone Synchronization Helper ---
def calculate_utc_schedule(target_hour: int, target_minute: int, user_iana_tz: str) -> tuple:
    """Transforms localized scheduling input strings into UTC parameters cleanly."""
    local_tz = pytz_timezone(user_iana_tz)
    # Target time on current day in local timezone
    now_local = datetime.now(local_tz)
    local_time = now_local.replace(
        hour=target_hour, 
        minute=target_minute, 
        second=0, 
        microsecond=0
    )
    utc_time = local_time.astimezone(timezone.utc)
    return utc_time.hour, utc_time.minute

# --- Background Task Runner with pessimistic row lock ---
async def run_agent_pipeline(ticker: str, user_id: str):
    """
    Executes the LangGraph pipeline for a specific stock ticker and user.
    Uses SELECT FOR UPDATE row-level locking to prevent concurrent executions.
    Logs output and execution metrics.
    """
    logger.info(f"Starting agent pipeline execution for {ticker} (User: {user_id})")
    start_time = time.time()
    status = "SUCCESS"
    error_log = None

    # Step 1: Pessimistic lock on the watchlist row to guard critical section
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                select(Watchlist)
                .where(Watchlist.ticker == ticker)
                .where(Watchlist.user_id == user_id)
                .with_for_update()
            )
            result = await session.execute(stmt)
            watchlist_item = result.scalar_one_or_none()

            if not watchlist_item:
                logger.warning(f"Ticker {ticker} not found in watchlist for user {user_id}. Skipping job.")
                return

            if watchlist_item.is_processing:
                logger.info(f"Ticker {ticker} (User: {user_id}) is already being processed by another thread. Skipping.")
                return

            # Lock the item
            watchlist_item.is_processing = True
            await session.commit()

    # Step 2: Invoke the LangGraph Multi-Agent Pipeline
    try:
        initial_state = {
            "ticker": ticker,
            "raw_financials": {},
            "scraped_articles": "",
            "final_markdown_report": "",
            "error": ""
        }
        
        final_state = await app_graph.ainvoke(initial_state)

        # Handle explicit errors from the state
        if final_state.get("error"):
            raise ValueError(final_state["error"])

        markdown_report = final_state.get("final_markdown_report", "")
        raw_financials = final_state.get("raw_financials", {})

        if not markdown_report:
            raise ValueError("Pipeline returned an empty markdown report.")

        # Step 3: Save Report & Unlock
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Store the report
                report = FinancialReport(
                    ticker=ticker,
                    owner_id=user_id,
                    generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    quantitative_metrics=raw_financials,
                    markdown_content=markdown_report
                )
                session.add(report)

                # Reset processing flag
                stmt = select(Watchlist).where(Watchlist.ticker == ticker).where(Watchlist.user_id == user_id)
                res = await session.execute(stmt)
                item = res.scalar_one_or_none()
                if item:
                    item.is_processing = False
                    item.last_error = None
                await session.commit()

    except Exception as e:
        status = "FAILED"
        error_log = str(e)
        logger.error(f"Pipeline crashed for ticker {ticker} (User: {user_id}): {error_log}", exc_info=True)

        # Step 4: Fallback Unlock and Save Error
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(Watchlist).where(Watchlist.ticker == ticker).where(Watchlist.user_id == user_id)
                res = await session.execute(stmt)
                item = res.scalar_one_or_none()
                if item:
                    item.is_processing = False
                    item.last_error = error_log
                await session.commit()

    finally:
        # Step 5: Save Job Execution Record
        execution_time_ms = int((time.time() - start_time) * 1000)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job_run = JobRun(
                    ticker=ticker,
                    triggered_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    status=status,
                    execution_time_ms=execution_time_ms,
                    error_log=error_log
                )
                session.add(job_run)
                await session.commit()

# --- Sync database active schedules to APScheduler ---
async def sync_watchlist_jobs_to_scheduler():
    """Reads all active schedules from the database and loads them into APScheduler."""
    logger.info("Syncing database watchlist schedules to APScheduler...")
    async with AsyncSessionLocal() as session:
        stmt = select(Watchlist).where(Watchlist.cron_hour.is_not(None)).where(Watchlist.cron_minute.is_not(None))
        result = await session.execute(stmt)
        watchlist_items = result.scalars().all()

        for item in watchlist_items:
            job_id = f"job_{item.user_id}_{item.ticker}"
            logger.info(f"Registering job {job_id} on cron at {item.cron_hour:02d}:{item.cron_minute:02d} UTC")
            try:
                scheduler.add_job(
                    run_agent_pipeline,
                    trigger='cron',
                    hour=item.cron_hour,
                    minute=item.cron_minute,
                    args=[item.ticker, item.user_id],
                    id=job_id,
                    replace_existing=True
                )
            except Exception as e:
                logger.error(f"Failed to register scheduled job {job_id}: {e}")

# --- APScheduler Lifecycle Management ---
job_stores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
}
job_defaults = {
    'coalesce': True,
    'max_instances': 1
}
scheduler = AsyncIOScheduler(jobstores=job_stores, job_defaults=job_defaults)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start scheduler and sync database jobs
    scheduler.start()
    await sync_watchlist_jobs_to_scheduler()
    yield
    # Shutdown: clean shutdown of scheduler
    scheduler.shutdown()

# Initialize FastAPI App
app = FastAPI(
    title="MarketInsight API Server",
    description="Autonomous scheduled financial analysis reports API",
    lifespan=lifespan
)

# CORS Middleware Configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, lock this down to the React frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency: Retrieve Request User ID ---
def get_current_user_id(request: Request) -> str:
    """Gets the authenticated user ID from headers, fallback to local-admin."""
    # We use a custom header to bypass local MVP auth while ensuring future IDOR compliance
    return request.headers.get("X-User-ID", "local-admin")

# --- Pydantic Schemes for API payloads ---
class WatchlistCreate(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol (e.g. AAPL, NVDA)")

class WatchlistSchedule(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    hour: int = Field(..., ge=0, le=23, description="Hour to trigger report (0-23)")
    minute: int = Field(..., ge=0, le=59, description="Minute to trigger report (0-59)")
    timezone: str = Field("UTC", description="IANA timezone name (e.g. America/New_York, UTC)")

# --- GLOBAL SECURITY EXCEPTION HANDLER ---
@app.exception_handler(Exception)
async def global_security_exception_handler(request: Request, exc: Exception):
    """Catches all unhandled exceptions, logs internally, and masks sensitive credentials."""
    logger.error(f"Critical System Error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "An internal server error occurred while processing the report."}
    )

# --- API ROUTES ---

@app.get("/api/watchlist")
async def get_watchlist(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """Fetch all stock tickers in the user's watchlist."""
    stmt = select(Watchlist).where(Watchlist.user_id == user_id)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return items

@app.post("/api/watchlist")
async def add_to_watchlist(
    payload: WatchlistCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Add a new ticker to the user's watchlist. Enforces max 5 quota limit."""
    ticker_upper = payload.ticker.strip().upper()
    if not ticker_upper:
        raise HTTPException(status_code=400, detail="Ticker symbol cannot be empty.")

    # 1. Enforce quota: count current items
    stmt_count = select(Watchlist).where(Watchlist.user_id == user_id)
    result_count = await db.execute(stmt_count)
    current_items = result_count.scalars().all()
    
    if len(current_items) >= 5:
        raise HTTPException(
            status_code=400, 
            detail="Watchlist quota exceeded. You can monitor a maximum of 5 active tickers."
        )

    # 2. Check if already exists in watchlist
    exists = any(item.ticker == ticker_upper for item in current_items)
    if exists:
        return {"status": "already_exists", "ticker": ticker_upper}

    # 3. Create database entry
    new_item = Watchlist(
        user_id=user_id,
        ticker=ticker_upper,
        is_processing=False
    )
    db.add(new_item)
    await db.commit()

    return {"status": "success", "watchlist_item": new_item}

@app.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Removes a ticker from the user's watchlist and cancels any scheduled jobs."""
    ticker_upper = ticker.strip().upper()
    
    # 1. Remove from database
    stmt = delete(Watchlist).where(Watchlist.ticker == ticker_upper).where(Watchlist.user_id == user_id)
    res = await db.execute(stmt)
    await db.commit()

    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticker not found in watchlist.")

    # 2. Remove job from scheduler
    job_id = f"job_{user_id}_{ticker_upper}"
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Cancelled schedule for {job_id}")
    except Exception as e:
        logger.error(f"Error removing scheduler job {job_id}: {e}")

    return {"status": "success", "removed_ticker": ticker_upper}

@app.post("/api/watchlist/schedule")
async def modify_stock_schedule(
    payload: WatchlistSchedule,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Saves or updates a recurring daily cron report schedule for a ticker."""
    ticker_upper = payload.ticker.strip().upper()

    # 1. Verify it exists in user's watchlist first
    stmt = select(Watchlist).where(Watchlist.ticker == ticker_upper).where(Watchlist.user_id == user_id)
    result = await db.execute(stmt)
    watchlist_item = result.scalar_one_or_none()

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="Ticker not found in watchlist. Add it first.")

    # 2. Calculate schedule in UTC using timezone synchronization helper
    try:
        utc_hour, utc_minute = calculate_utc_schedule(payload.hour, payload.minute, payload.timezone)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid timezone or time values: {e}")

    # 3. Update watchlist DB model
    watchlist_item.cron_hour = utc_hour
    watchlist_item.cron_minute = utc_minute
    await db.commit()

    # 4. Schedule job in APScheduler
    job_id = f"job_{user_id}_{ticker_upper}"
    scheduler.add_job(
        run_agent_pipeline,
        trigger='cron',
        hour=utc_hour,
        minute=utc_minute,
        args=[ticker_upper, user_id],
        id=job_id,
        replace_existing=True
    )

    logger.info(f"Scheduled cron job {job_id} at {utc_hour:02d}:{utc_minute:02d} UTC (Local {payload.hour:02d}:{payload.minute:02d} {payload.timezone})")

    return {
        "status": "success", 
        "scheduled_ticker": ticker_upper,
        "utc_time": f"{utc_hour:02d}:{utc_minute:02d}",
        "local_time": f"{payload.hour:02d}:{payload.minute:02d}",
        "timezone": payload.timezone
    }

@app.post("/api/watchlist/trigger/{ticker}")
async def trigger_report_manually(
    ticker: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Triggers report generation for a stock immediately in the background."""
    ticker_upper = ticker.strip().upper()

    # 1. Check if the ticker exists in the user's watchlist
    stmt = select(Watchlist).where(Watchlist.ticker == ticker_upper).where(Watchlist.user_id == user_id)
    result = await db.execute(stmt)
    watchlist_item = result.scalar_one_or_none()

    if not watchlist_item:
        raise HTTPException(status_code=404, detail="Ticker not found in watchlist. Add it first.")

    if watchlist_item.is_processing:
        return {"status": "already_running", "message": f"Report generation is currently running for {ticker_upper}."}

    # 2. Add pipeline execution to background tasks
    background_tasks.add_task(run_agent_pipeline, ticker_upper, user_id)
    
    return {"status": "triggered", "message": f"Report generation started for {ticker_upper}."}

@app.get("/api/reports")
async def list_reports(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """List metadata for all reports generated by the user (chronological sidebar)."""
    # Return reports sorted in descending order of generation date
    stmt = (
        select(FinancialReport.id, FinancialReport.ticker, FinancialReport.generated_at)
        .where(FinancialReport.owner_id == user_id)
        .order_by(desc(FinancialReport.generated_at))
    )
    result = await db.execute(stmt)
    reports = result.all()
    # Format database rows as list of dicts
    return [{"id": r.id, "ticker": r.ticker, "generated_at": r.generated_at} for r in reports]

@app.get("/api/reports/{ticker}")
async def get_latest_report(
    ticker: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the latest financial report generated for a specific stock ticker."""
    ticker_upper = ticker.strip().upper()
    stmt = (
        select(FinancialReport)
        .where(FinancialReport.ticker == ticker_upper)
        .where(FinancialReport.owner_id == user_id)
        .order_by(desc(FinancialReport.generated_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail=f"No reports generated yet for {ticker_upper}.")

    return report

@app.get("/api/reports/id/{id}")
async def get_report_by_id(
    id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a specific report by its unique ID."""
    stmt = (
        select(FinancialReport)
        .where(FinancialReport.id == id)
        .where(FinancialReport.owner_id == user_id)
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    return report

@app.get("/api/jobs")
async def get_job_runs(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get recent job runs (audit log) associated with tickers in the user's watchlist."""
    # Ensure IDOR prevention by only listing runs for tickers the user is watching
    stmt = (
        select(JobRun)
        .where(JobRun.ticker.in_(
            select(Watchlist.ticker).where(Watchlist.user_id == user_id)
        ))
        .order_by(desc(JobRun.triggered_at))
        .limit(50) # Return last 50 entries
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return runs
