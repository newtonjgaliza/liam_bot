import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from src.handlers.auth import check_auth
from src.services.ai_service import (
    analyze_message_intent,
    answer_health_query,
)
from src.database import (
    get_or_create_user,
    add_appointment,
    get_recent_documents,
    get_upcoming_appointments,
    get_all_medications,
)
from src.config import TIMEZONE

logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processa mensagens de texto recebidas pelo Liam:
    - Agendamento de consultas ("liam tenho uma consulta dia 12 de dezembro...")
    - Perguntas sobre o histórico ("liam quais remédios a dra flavia passou...")
    - Bate-papo casual e orientações
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
        # Analisa a intenção da mensagem com o Gemini
        analysis = await analyze_message_intent(text, user.first_name or "Usuário")
        intent = analysis.get("intent", "CHAT")

        # 1. CASO SEJA AGENDAMENTO DE CONSULTA
        if intent == "APPOINTMENT":
            apt_details = analysis.get("appointment_details", {})
            date_str = apt_details.get("date")
            time_str = apt_details.get("time")

            if not date_str:
                await message.reply_text(
                    "Entendi que você quer anotar uma consulta, mas não consegui identificar a data com certeza. "
                    "Poderia me confirmar o dia e horário? (Ex: _\"dia 12 de dezembro às 14h\"_)",
                    parse_mode="Markdown"
                )
                return

            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                await message.reply_text(
                    f"Tive dúvida no formato da data ({date_str}). Poderia me confirmar a data da consulta?",
                    parse_mode="Markdown"
                )
                return

            parsed_time = None
            if time_str:
                try:
                    parsed_time = datetime.strptime(time_str, "%H:%M").time()
                except ValueError:
                    pass

            patient_name = apt_details.get("patient_name") or user.first_name
            doctor_name = apt_details.get("doctor_name") or "Médico não especificado"
            specialty = apt_details.get("specialty")
            location = apt_details.get("location")
            notes = apt_details.get("notes")

            # Salva no banco de dados
            await add_appointment(
                patient_name=patient_name,
                doctor_name=doctor_name,
                specialty=specialty,
                appointment_date=parsed_date,
                appointment_time=parsed_time,
                location=location,
                notes=notes,
                telegram_chat_id=message.chat_id,
            )

            time_formatted = parsed_time.strftime("%H:%M") if parsed_time else "Horário a definir"
            date_formatted = parsed_date.strftime("%d/%m/%Y")

            confirm_msg = (
                f"✅ *Consulta anotada com sucesso!*\n\n"
                f"📅 *Data:* {date_formatted}\n"
                f"⏰ *Horário:* {time_formatted}\n"
                f"👨‍⚕️ *Médico(a):* {doctor_name}"
            )
            if specialty:
                confirm_msg += f" ({specialty})"
            confirm_msg += f"\n👤 *Paciente:* {patient_name}"
            if location:
                confirm_msg += f"\n📍 *Local:* {location}"
            if notes:
                confirm_msg += f"\n📝 *Obs:* {notes}"

            confirm_msg += (
                f"\n\n🔔 *Fique tranquilo(a)!* Eu vou te avisar no dia anterior e "
                f"no próprio dia {date_formatted} para você não esquecer!"
            )
            await message.reply_text(confirm_msg, parse_mode="Markdown")
            return

        # 2. CASO SEJA UMA PERGUNTA SOBRE O HISTÓRICO
        elif intent == "QUERY":
            now = datetime.now(TIMEZONE)
            recent_docs = await get_recent_documents(limit=15)
            upcoming_apts = await get_upcoming_appointments(from_date=now.date())
            all_meds = await get_all_medications(limit=40)

            reply = await answer_health_query(
                query=text,
                user_name=user.first_name or "Usuário",
                recent_documents=recent_docs,
                upcoming_appointments=upcoming_apts,
                medications=all_meds,
            )
            await message.reply_text(reply)
            return

        # 3. CONVERSA GERAL / BATE-PAPO
        else:
            chat_reply = analysis.get("chat_reply")
            if not chat_reply:
                chat_reply = (
                    "Estou aqui para ajudar você e sua esposa com consultas, receitas e saúde! "
                    "Pode me mandar datas de consultas, arquivos de receitas ou tirar dúvidas sobre o histórico."
                )
            await message.reply_text(chat_reply)

    except Exception as e:
        logger.error(f"Erro ao processar mensagem de texto: {e}", exc_info=True)
        await message.reply_text(
            f"Desculpe, tive um problema ao processar sua mensagem: {str(e)}"
        )
