import os
import sys
import warnings

# Suppress LangGraph/LangChain pending-deprecation noise before any langgraph import
warnings.filterwarnings("ignore", message=r".*allowed_objects.*")
# Suppress the cosmetic ChatVertexAI deprecation warning. We intentionally use
# ChatVertexAI (Vertex AI exclusivity per MODELS.MD); the suggested
# ChatGoogleGenerativeAI replacement is a different auth path we don't want here.
# The warning is emitted as two categories — a plain DeprecationWarning ("Use
# ChatGoogleGenerativeAI instead") and a LangChainDeprecationWarning — so we
# silence by category, scoped to the ChatVertexAI message, to keep logs clean.
warnings.filterwarnings(
    "ignore", message=r".*ChatVertexAI.*", category=DeprecationWarning
)
try:
    from langchain_core._api.deprecation import LangChainDeprecationWarning as _LCDW

    warnings.filterwarnings("ignore", message=r".*ChatVertexAI.*", category=_LCDW)
except Exception:
    # langchain_core not importable yet / API moved — fall back to message-only.
    warnings.filterwarnings("ignore", message=r".*ChatVertexAI.*")
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rich.console import Console
from rich.logging import RichHandler
import logging

from dotenv import load_dotenv, find_dotenv

# Search for the .env file starting from the root of the project
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings(BaseSettings):
    # Logging
    ENABLE_LOGS: bool = os.getenv("ENABLE_LOGS", "True").lower() in ("true", "1", "t")

    # DB Configuration
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")

    # Vertex AI Configuration
    USE_VERTEX: bool = os.getenv("USE_VERTEX", "false").lower() in ("true", "1", "t")
    GOOGLE_CLOUD_PROJECT: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    # LLM Configuration (Gemini Flash)
    LLM_API_KEY_1: str = os.getenv(
        "GOOGLE_API_KEY_1", os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    )
    LLM_API_KEY_2: str = os.getenv("GOOGLE_API_KEY_2", "")
    LLM_API_KEY_3: str = os.getenv("GOOGLE_API_KEY_3", "")
    LLM_MODEL_NAME: str = "gemini-3.1-flash-lite"

    # Public base URL the frontend should call. Blank = same origin as the
    # page (the normal case, since FastAPI serves the frontend itself).
    # Set only when the frontend is hosted on a different origin than the API.
    PUBLIC_API_BASE_URL: str = os.getenv("PUBLIC_API_BASE_URL", "")

    # Discovery hard-filter thresholds (Stage 6) — tunable via env without redeploy
    DISCOVERY_HARD_MIN_MCAP: int = int(
        os.getenv("DISCOVERY_HARD_MIN_MCAP", "5000000000")
    )  # ₹500 Cr
    DISCOVERY_HARD_MIN_AVG_VOL: int = int(
        os.getenv("DISCOVERY_HARD_MIN_AVG_VOL", "500000")
    )  # 5 lakh shares
    DISCOVERY_HARD_MIN_PRICE: int = int(
        os.getenv("DISCOVERY_HARD_MIN_PRICE", "50")
    )  # ₹50

    # ── Arize Phoenix Cloud Observability (Phase 3) ──────────────
    ARIZE_ENABLED: bool = os.getenv("ARIZE_ENABLED", "false").lower() in (
        "true",
        "1",
        "t",
    )
    PHOENIX_API_KEY: str = os.getenv("PHOENIX_API_KEY", "")
    PHOENIX_COLLECTOR_ENDPOINT: str = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "")
    PHOENIX_PROJECT_NAME: str = os.getenv("PHOENIX_PROJECT_NAME", "arthavest")

    # Deployment flag to skip startup DB verification check
    DEPLOYED: bool = (
        os.getenv("DEPLOYED", "false").lower() in ("true", "1", "t")
        or "RENDER" in os.environ
    )

    # ── Arize Phoenix MCP Self-improving Loop (Phase 7) ─────────
    ARIZE_MCP_ENABLED: bool = os.getenv("ARIZE_MCP_ENABLED", "false").lower() in (
        "true",
        "1",
        "t",
    )
    PHOENIX_SPACE_SUFFIX: str = os.getenv(
        "PHOENIX_SPACE_SUFFIX", ""
    )  # e.g. "rushilvmehta999"

    # MCP Client Configuration
    MCP_SERVER_URL: str = os.getenv(
        "MCP_SERVER_URL", ""
    )
    MCP_TIMEOUT: int = int(os.getenv("MCP_TIMEOUT", "45"))
    MCP_RETRIES: int = int(os.getenv("MCP_RETRIES", "2"))
    MCP_HEALTH_TTL: int = int(os.getenv("MCP_HEALTH_TTL", "15"))
    DISABLE_MCP_FALLBACK: bool = os.getenv("DISABLE_MCP_FALLBACK", "false").lower() in (
        "true",
        "1",
        "t",
    )


settings = Settings()

# ==========================================
# 1. SETUP LOGGING (Rich Library)
# ==========================================
# On Windows the default console codec is cp1252, which raises
# UnicodeEncodeError when Rich tries to emit emoji/box-drawing chars (✗, 🚀, ℹ).
# That error escapes through the logging handler and can surface as a bare
# HTTP 500 from any request whose code path logs such a character. Force the
# underlying stdout to UTF-8 so logging can never crash a request.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # py3.7+
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
console = Console(file=sys.stdout)


def get_logger(name: str):
    logger = logging.getLogger(name)
    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    if settings.ENABLE_LOGS:
        logger.setLevel(logging.INFO)
        rich_handler = RichHandler(console=console, rich_tracebacks=True, markup=True)
        rich_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(rich_handler)
    else:
        # Disable logging if not enabled in .env
        logger.addHandler(logging.NullHandler())
        logger.propagate = False

    return logger


logger = get_logger("quant_ai")

# ==========================================
# 2. SETUP DATABASE
# ==========================================
try:
    db_url = settings.DATABASE_URL
    if not db_url:
        raise ValueError(
            "DATABASE_URL environment variable is not set! Please configure your Amazon Aurora PostgreSQL connection."
        )

    # Ensure standard postgresql URL if needed (some drivers need postgresql+psycopg2)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    logger.info("[bold cyan]Attempting to initialize database engine...[/bold cyan]")
    engine_kwargs = {"pool_pre_ping": True}
    if not db_url.startswith("sqlite"):
        engine_kwargs.update({"pool_recycle": 300, "pool_size": 20, "max_overflow": 10})
    engine = create_engine(db_url, **engine_kwargs)
    if not settings.DEPLOYED:
        with engine.connect() as conn:
            logger.info(
                "[bold green]OK Database connection verified successfully.[/bold green]"
            )
    else:
        logger.info(
            "[bold yellow]DEPLOYED is True: skipping startup database connection verification check.[/bold yellow]"
        )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.error(f"[bold red]✗ Database connection failed: {e}[/bold red]")
    # Maintain SessionLocal as None or similar to avoid crash later,
    # but the error is now prominent.
    SessionLocal = None


def get_db():
    if SessionLocal is None:
        logger.error(
            "[bold red]Cannot get DB session: SessionLocal is not initialized.[/bold red]"
        )
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# 3. SETUP LLM PREVIEW
# ==========================================
def get_llm_info():
    if not settings.LLM_API_KEY_1:
        logger.warning(
            "[bold yellow]⚠ LLM_API_KEY_1 is not set. LLM features may fail.[/bold yellow]"
        )
    else:
        logger.info(
            f"[bold blue]ℹ LLM Configuration: {settings.LLM_MODEL_NAME}[/bold blue]"
        )

    return {"model": settings.LLM_MODEL_NAME, "status": "initialized"}
