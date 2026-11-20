"""Application settings, read from environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Settings:
    APP_NAME = _env("APP_NAME", "BU AI")
    APP_TAGLINE = _env("APP_TAGLINE", "Intelligent Student Success Platform")
    UNIVERSITY = _env("UNIVERSITY_NAME", "Belhaven University")

    DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")
    # Hosts such as Render give "postgres://..."; SQLAlchemy with psycopg 3 needs "postgresql+psycopg://".
    if DATABASE_URL.startswith(("postgres://", "postgresql://")):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
    SEED_FILE = BASE_DIR / "data" / "seed_kb.json"

    # none | openai | azure | anthropic
    LLM_PROVIDER = _env("LLM_PROVIDER", "none").lower()
    # Embeddings provider for vector search: auto | openai | azure | none
    EMBEDDINGS_PROVIDER = _env("EMBEDDINGS_PROVIDER", "auto").lower()   # auto | openai | azure | local | none
    LOCAL_EMBED_MODEL = _env("LOCAL_EMBED_MODEL", str(BASE_DIR / "models" / "potion-base-8M"))

    OPENAI_API_KEY = _env("OPENAI_API_KEY")
    OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_EMBED_MODEL = _env("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    AZURE_OPENAI_ENDPOINT = _env("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = _env("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2024-10-21")
    AZURE_OPENAI_DEPLOYMENT = _env("AZURE_OPENAI_DEPLOYMENT")
    AZURE_OPENAI_EMBED_DEPLOYMENT = _env("AZURE_OPENAI_EMBED_DEPLOYMENT")

    ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    ADMIN_TOKEN = _env("ADMIN_TOKEN", "")

    # Abuse and cost protection
    CHAT_RATE_PER_MINUTE = int(_env("CHAT_RATE_PER_MINUTE", "12"))   # per client IP
    DAILY_AI_LIMIT = int(_env("DAILY_AI_LIMIT", "2000"))             # AI calls per day; then official-text answers
    MAX_CONCURRENT_PER_IP = int(_env("MAX_CONCURRENT_PER_IP", "2"))   # simultaneous answers per visitor
    VERIFY_WITH_AI = _env("VERIFY_WITH_AI", "false").lower() == "true"  # second AI pass to review each answer
    TRUST_PROXY = _env("TRUST_PROXY", "false").lower() == "true"     # use X-Forwarded-For behind a proxy

    # Automatic refresh: re-crawl the website every N hours inside the API (0 = off),
    # and pick up content changes made by a separate crawler process every N seconds.
    CRAWL_EVERY_HOURS = float(_env("CRAWL_EVERY_HOURS", "0"))
    INDEX_WATCH_SECONDS = int(_env("INDEX_WATCH_SECONDS", "60"))
    # A bare host name (as a hosting blueprint provides) means its https:// origin.
    # A bare host name (as a hosting blueprint provides) means its https:// origin; a Render-internal name
    # without a domain ("bu-ai-web") means its public onrender.com address.
    CORS_ORIGINS = [o.strip() if "://" in o else (f"https://{o.strip()}" if "." in o else f"https://{o.strip()}.onrender.com")
                    for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

    # Crawler
    CRAWL_SEEDS = [s for s in _env(
        "CRAWL_SEEDS",
        "https://www.belhaven.edu/,https://www.belhaven.edu/current-students/index.html,"
        "https://www.belhaven.edu/international/index.html,https://igsupport.belhaven.edu/kb/index.php,"
        "https://www.belhaven.edu/academics/resources/academic-calendar.html,https://www.belhaven.edu/academics/program-finder/index.html,"
        "https://www.belhaven.edu/admission/undergrad/aid/index.html,https://www.belhaven.edu/admission/online/index.html",
    ).split(",") if s]
    CRAWL_ALLOWED_HOSTS = [h for h in _env(
        "CRAWL_ALLOWED_HOSTS", "www.belhaven.edu,belhaven.edu,igsupport.belhaven.edu").split(",") if h]
    CRAWLED_FILE = BASE_DIR / "data" / "crawled_pages.json.gz"   # written by the crawl job, loaded at startup
    CRAWL_MAX_PAGES = int(_env("CRAWL_MAX_PAGES", "400"))
    CRAWL_DELAY_SECONDS = float(_env("CRAWL_DELAY_SECONDS", "1.0"))
    CRAWL_USER_AGENT = _env(
        "CRAWL_USER_AGENT", "StudentSuccessPrototypeBot/0.1 (independent student research prototype)")


settings = Settings()
