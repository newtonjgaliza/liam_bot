import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from src.config import TELEGRAM_BOT_TOKEN
from src.handlers.start import (
    start_command,
    help_command,
    list_appointments_command,
    list_medications_command,
)
from src.handlers.documents import handle_document_or_photo
from src.handlers.chat import handle_text_message
from src.services.scheduler import check_appointment_reminders

logger = logging.getLogger(__name__)


def create_bot_app() -> Application:
    """Cria e configura a aplicação do Telegram Bot."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("consultas", list_appointments_command))
    app.add_handler(CommandHandler("remedios", list_medications_command))

    # Documentos e Fotos (PDFs, receitas, dietas, etc.)
    app.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.PHOTO,
            handle_document_or_photo
        )
    )

    # Mensagens de texto (Agendamentos em linguagem natural e perguntas)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text_message
        )
    )

    # Agendador de Lembretes (roda a cada 5 minutos = 300s)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            check_appointment_reminders,
            interval=300,
            first=10,
            name="check_reminders_job"
        )
        logger.info("Job de lembretes configurado com sucesso (a cada 5 minutos).")
    else:
        logger.warning("JobQueue não está disponível. Certifique-se de instalar python-telegram-bot[job-queue].")

    return app
