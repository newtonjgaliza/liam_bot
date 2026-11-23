import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.handlers.auth import check_auth
from src.services.ai_service import chat_with_agent
from src.database import get_or_create_user

logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processa mensagens de texto recebidas pelo Liam via Agente com Tools:
    - Agendamento de consultas via ferramenta agendar_consulta
    - Busca de histórico de receitas/remédios via ferramenta buscar_historico_medico
    - Listagem de consultas via ferramenta listar_consultas
    - Cancelamento via ferramenta cancelar_consulta
    - Conversação natural e acolhedora
    """
    if not check_auth(update):
        return

    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    user = update.effective_user
    await get_or_create_user(user.id, user.first_name)

    # Indicador de "digitando..."
    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    try:
        reply = await chat_with_agent(
            user_message=text,
            user_name=user.first_name or "Usuário",
            telegram_chat_id=message.chat_id,
        )
        await message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro ao processar mensagem com agente: {e}", exc_info=True)
        # Fallback sem formatação Markdown se houver erro de sintaxe
        try:
            await message.reply_text(reply)
        except Exception:
            await message.reply_text(f"Desculpe, tive uma falha ao responder: {str(e)}")
