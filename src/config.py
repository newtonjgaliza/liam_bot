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

DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'liam.db'}"
)
