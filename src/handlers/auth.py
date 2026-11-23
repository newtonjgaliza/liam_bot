from typing import Callable
from telegram import Update
from telegram.ext import ContextTypes
from src.config import ALLOWED_TELEGRAM_IDS


def check_auth(update: Update) -> bool:
    """Verifica se o usuário que enviou a mensagem tem permissão."""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if not ALLOWED_TELEGRAM_IDS:
        return True
    return user_id in ALLOWED_TELEGRAM_IDS
