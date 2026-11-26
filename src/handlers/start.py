from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from src.handlers.auth import check_auth
from src.database import (
    get_or_create_user,
    get_upcoming_appointments,
    get_all_medications,
    get_all_dietary_profiles,
)
from src.config import TIMEZONE


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipulador do comando /start."""
    if not check_auth(update):
        await update.message.reply_text(
            "Desculpe! Eu sou o Liam, um assistente médico privado para a família. "
            f"Seu ID do Telegram é `{update.effective_user.id}`. "
            "Peça ao proprietário para adicionar seu ID à lista de autorizados.",
            parse_mode="Markdown"
        )
        return

    user = update.effective_user
    await get_or_create_user(user.id, user.first_name)

    welcome_text = (
        f"👋 Olá, {user.first_name}! Eu sou o *Liam*, o assistente de saúde e consultas de vocês!\n\n"
        "Aqui está o que você pode fazer comigo:\n\n"
        "📅 *Agendar consultas e exames:*\n"
        "• Basta me dizer naturalmente, por exemplo:\n"
        "  _\"Liam, tenho uma consulta dia 12 de dezembro às 14h com a Dra. Flávia\"_\n"
        "  _\"Marquei cardiologista dia 20/01 para minha esposa\"_\n"
        "  *(Eu vou te lembrar na véspera, no dia pela manhã e 2 horas antes!)*\n\n"
        "📄 *Guardar receitas, dietas e exames:*\n"
        "• Me mande o *PDF* ou a *foto* da receita/exame.\n"
        "• Eu leio tudo, identifico os remédios, dosagens e guardo com segurança.\n\n"
        "💬 *Perguntar sobre o histórico:*\n"
        "• _\"Liam, quais remédios a Dra. Flávia passou na última consulta?\"_\n"
        "• _\"Qual foi a recomendação da nutricionista para o café da manhã?\"_\n"
        "• _\"Quais são as minhas próximas consultas?\"_\n\n"
        "📌 *Comandos úteis:*\n"
        "/consultas - Ver próximas consultas agendadas\n"
        "/remedios - Ver medicamentos salvos no histórico\n"
        "/dieta - Ver restrições alimentares de Newton e Janaína\n"
        "/ajuda - Relembrar o que posso fazer\n\n"
        "🥗 *Analisar Rótulos e Ingredientes:*\n"
        "• Tire uma foto dos ingredientes de qualquer alimento e me envie!\n"
        "• Na legenda, você pode dizer:\n"
        "  _\"eu posso comer isso?\"_ ou _\"janaina pode comer isso?\"_\n"
        "  *(Eu analiso os ingredientes e respondo com o veredito instantâneo 🟢🟡🔴)*"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipulador do comando /ajuda."""
    if not check_auth(update):
        return
    await start_command(update, context)


async def list_appointments_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /consultas: Lista as próximas consultas."""
    if not check_auth(update):
        return

    now = datetime.now(TIMEZONE)
    appointments = await get_upcoming_appointments(from_date=now.date())

    if not appointments:
        await update.message.reply_text(
            "📅 Nenhuma consulta futura registrada no momento.\n"
            "Para agendar uma, basta me mandar uma mensagem como:\n"
            "_\"Liam, marquei dentista dia 15/02 às 10h\"_",
            parse_mode="Markdown"
        )
        return

    text = "🗓️ *Próximas Consultas Agendadas:*\n\n"
    for apt in appointments:
        date_str = apt.appointment_date.strftime("%d/%m/%Y")
        time_str = apt.appointment_time.strftime("%H:%M") if apt.appointment_time else "Sem horário definido"
        text += (
            f"• *{date_str} às {time_str}*\n"
            f"  👨‍⚕️ *Médico:* {apt.doctor_name} ({apt.specialty or 'Especialidade n/i'})\n"
            f"  👤 *Paciente:* {apt.patient_name}\n"
        )
        if apt.location:
            text += f"  📍 *Local:* {apt.location}\n"
        if apt.notes:
            text += f"  📝 *Obs:* {apt.notes}\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def list_medications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /remedios: Lista os medicamentos cadastrados."""
    if not check_auth(update):
        return

    medications = await get_all_medications(limit=30)
    if not medications:
        await update.message.reply_text(
            "💊 Nenhum medicamento cadastrado no histórico ainda.\n"
            "Quando tiver uma receita médica, basta me enviar o PDF ou a foto dela!",
            parse_mode="Markdown"
        )
        return

    text = "💊 *Medicamentos Registrados no Histórico:*\n\n"
    for med in medications:
        date_str = med.prescription_date.strftime("%d/%m/%Y") if med.prescription_date else "Data n/i"
        text += (
            f"• *{med.name}* ({med.dosage or 'Dosagem n/i'})\n"
            f"  👤 *Paciente:* {med.patient_name} | 👨‍⚕️ {med.doctor_name or 'Médico n/i'}\n"
            f"  ⏰ *Frequência:* {med.frequency or 'n/i'} (Receitado em: {date_str})\n"
        )
        if med.instructions:
            text += f"  📋 *Instruções:* {med.instructions}\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def dietary_restrictions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /dieta e /restricoes: Exibe o perfil alimentar e restrições de Newton e Janaína."""
    if not check_auth(update):
        return

    profiles = await get_all_dietary_profiles()
    if not profiles:
        await update.message.reply_text("Nenhum perfil de dieta encontrado no momento.")
        return

    text = "🥗 *Perfis de Restrições Alimentares Cadastrados:*\n\n"
    for p in profiles:
        text += f"👤 *Paciente:* *{p.patient_name.upper()}*\n"
        text += f"🚫 *Proibidos:* {p.prohibited_items}\n\n"
        text += f"⚠️ *Atenção / Limite:* {p.restricted_items}\n\n"
        text += f"🟢 *Permitidos:* {p.allowed_items}\n\n"
        if p.notes:
            text += f"🎯 *Metas & Obs:* _{p.notes}_\n\n"
        text += "----------------------------------------\n\n"

    text += (
        "💡 *Como testar rótulos no mercado:*\n"
        "Tire uma foto dos ingredientes de qualquer embalagem e mande para mim!\n"
        "Na legenda, você pode colocar: _\"eu posso comer isso?\"_ ou _\"janaina pode comer isso?\"_."
    )

    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text)

