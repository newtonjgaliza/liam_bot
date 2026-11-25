import os
from pathlib import Path
from dotenv import load_dotenv
import pytz

# Carrega variáveis do arquivo .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("A variável TELEGRAM_BOT_TOKEN não foi informada no arquivo .env!")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Usuários autorizados (IDs numéricos do Telegram)
_allowed_ids_raw = os.getenv("ALLOWED_TELEGRAM_IDS", "").strip()
ALLOWED_TELEGRAM_IDS = [
    int(uid.strip()) for uid in _allowed_ids_raw.split(",") if uid.strip().isdigit()
]

# Fuso horário
TIMEZONE_STR = os.getenv("TIMEZONE", "America/Sao_Paulo")
try:
    TIMEZONE = pytz.timezone(TIMEZONE_STR)
except Exception:
    TIMEZONE = pytz.timezone("America/Sao_Paulo")

# Porta do webserver (para Render)
PORT = int(os.getenv("PORT", "8080"))

# Diretórios de persistência
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

_raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if not _raw_db_url:
    DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'liam.db'}"
else:
    # Remove parâmetros específicos do Prisma (ex: ?pgbouncer=true) incompatíveis com asyncpg
    _raw_db_url = _raw_db_url.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")
    if _raw_db_url.endswith("?"):
        _raw_db_url = _raw_db_url[:-1]

    # Normaliza URLs do Postgres (ex: Supabase fornece postgres:// ou postgresql://)
    if _raw_db_url.startswith("postgres://"):
        DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+"):
        DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = _raw_db_url
