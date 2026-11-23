import logging
from datetime import datetime, timedelta, date, time
from telegram.ext import ContextTypes
from sqlalchemy import select
from src.config import TIMEZONE
from src.database import AsyncSessionLocal, Appointment

logger = logging.getLogger(__name__)


async def check_appointment_reminders(context: ContextTypes.DEFAULT_TYPE):
    """
    Tarefa periódica (executada a cada 5 ou 10 minutos) que checa se há consultas
    próximas e dispara os lembretes apropriados no Telegram.
    """
    now = datetime.now(TIMEZONE)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        # Busca consultas de hoje e amanhã
        stmt = (
            select(Appointment)
            .where(Appointment.appointment_date.in_([today, tomorrow]))
        )
        result = await session.execute(stmt)
        appointments = result.scalars().all()

        for apt in appointments:
            time_str = apt.appointment_time.strftime("%H:%M") if apt.appointment_time else "Horário não definido"
            header = f"🩺 *Consulta de {apt.patient_name}*\n👨‍⚕️ *Médico(a):* {apt.doctor_name}"
            if apt.specialty:
                header += f" ({apt.specialty})"
            if apt.location:
                header += f"\n📍 *Local:* {apt.location}"
            if apt.notes:
                header += f"\n📝 *Observações:* {apt.notes}"

            # 1. Lembrete de véspera (1 dia antes, a partir das 09:00)
            if apt.appointment_date == tomorrow and not apt.reminded_day_before:
                if now.hour >= 9:
                    msg = (
                        f"🔔 *Lembrete: Consulta Amanhã!*\n\n"
                        f"{header}\n"
                        f"📅 *Data:* Amanhã ({tomorrow.strftime('%d/%m/%Y')}) às {time_str}\n\n"
                        f"Não esqueça de separar exames ou receitas anteriores se necessário! 😊"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=apt.telegram_chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                        apt.reminded_day_before = True
                    except Exception as e:
                        logger.error(f"Erro ao enviar lembrete de véspera: {e}")

            # 2. Lembrete do dia pela manhã (a partir das 08:00)
            if apt.appointment_date == today and not apt.reminded_day_of:
                if now.hour >= 8:
                    msg = (
                        f"☀️ *Bom dia! Hoje tem consulta!*\n\n"
                        f"{header}\n"
                        f"⏰ *Horário:* {time_str}\n\n"
                        f"Liam passando para te ajudar a não esquecer! Tenha um ótimo dia."
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=apt.telegram_chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                        apt.reminded_day_of = True
                    except Exception as e:
                        logger.error(f"Erro ao enviar lembrete do dia: {e}")

            # 3. Lembrete de 2 horas antes (se tiver horário definido)
            if apt.appointment_date == today and apt.appointment_time and not apt.reminded_hours_before:
                apt_dt = datetime.combine(apt.appointment_date, apt.appointment_time)
                apt_dt = TIMEZONE.localize(apt_dt)
                diff = apt_dt - now

                # Dispara se faltar entre 15 minutos e 2 horas
                if timedelta(minutes=0) <= diff <= timedelta(hours=2):
                    msg = (
                        f"⏰ *Atenção! Sua consulta é daqui a pouco!*\n\n"
                        f"{header}\n"
                        f"⏰ *Horário marcado:* {time_str}\n\n"
                        f"Hora de se organizar para sair com calma!"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=apt.telegram_chat_id,
                            text=msg,
                            parse_mode="Markdown"
                        )
                        apt.reminded_hours_before = True
                    except Exception as e:
                        logger.error(f"Erro ao enviar lembrete de 2 horas: {e}")

        await session.commit()
