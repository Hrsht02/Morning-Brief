import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .database import Base, engine, SessionLocal, run_additive_migrations
from .config import settings
from .seed import run_seed, get_setting, set_setting
from .routers import auth, users, editions, categories, admin, scheduler, api_v1
from .routers import operations, sandbox, diagnostics
from .services.runtime_scheduler import start_runtime_scheduler, stop_runtime_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("morning_brief")

app = FastAPI(title="Morning Brief API", description="Country-aware LLM-powered daily news digest.", version="2.0.0")

VERCEL_PREVIEW_ORIGIN_REGEX = r"^https://morning-brief-[a-z0-9]+-harshit-kumars-projects-ed3c626f\.vercel\.app$"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=VERCEL_PREVIEW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our end. Please try again."})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Invalid request", "errors": errors})

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_additive_migrations()
    db = SessionLocal()
    try:
        run_seed(db)
        # Add new schedule settings without overwriting existing administrator choices.
        if not get_setting(db, "email_send_time", ""):
            set_setting(db, "email_send_time", get_setting(db, "email_send_window_start", "06:00"), "Exact daily production email trigger time in admin timezone, HH:MM")
        if not get_setting(db, "final_ingestion_time", ""):
            set_setting(db, "final_ingestion_time", f"{get_setting(db, 'final_ingestion_hour', '23').zfill(2)}:00", "Admin-configured final ingestion/deadline time in HH:MM")
        db.commit()
    except Exception as exc:
        logger.error("Seeding failed (app will still start): %s", exc)
    finally:
        db.close()
    start_runtime_scheduler()
    logger.info("Morning Brief API started successfully.")

@app.on_event("shutdown")
def on_shutdown():
    stop_runtime_scheduler()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(editions.router)
app.include_router(categories.router)
app.include_router(admin.router)
app.include_router(operations.router)
app.include_router(sandbox.router)
app.include_router(scheduler.router)
app.include_router(api_v1.router)
app.include_router(diagnostics.router)

@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": app.version}

@app.get("/", tags=["health"])
def root():
    return {"message": "Morning Brief API is running. See /docs for the API reference."}
