import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from src.handlers.auth import check_auth
from src.services.ai_service import process_medical_document
from src.database import add_document_with_medications, get_or_create_user
from src.config import UPLOADS_DIR

logger = logging.getLogger(__name__)


async def handle_document_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processa documentos (PDFs) e fotos de receitas, dietas ou exames.
    """
    if not check_auth(update):
        return

    message = update.message
    user = update.effective_user
    await get_or_create_user(user.id, user.first_name)

    file_obj = None
    file_name = "arquivo"
    mime_type = "application/octet-stream"

    status_msg = await message.reply_text("📥 Recebi seu arquivo! Estou lendo e analisando com atenção...")

    try:
        if message.document:
            file_obj = await message.document.get_file()
            file_name = message.document.file_name or "documento.pdf"
            mime_type = message.document.mime_type or "application/pdf"
            file_id = message.document.file_id
        elif message.photo:
            # Pega a foto de maior resolução
            photo = message.photo[-1]
            file_obj = await photo.get_file()
            file_name = f"foto_{photo.file_unique_id}.jpg"
            mime_type = "image/jpeg"
            file_id = photo.file_id
        else:
            await status_msg.edit_text("Formato não suportado. Por favor, envie um PDF ou foto da receita/exame.")
            return

        # Baixa os bytes do arquivo
        file_bytes = await file_obj.download_as_bytearray()

        # Salva cópia local no diretório uploads (opcional)
        local_path = UPLOADS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"
        try:
            with open(local_path, "wb") as f:
                f.write(file_bytes)
            local_path_str = str(local_path)
        except Exception:
            local_path_str = None

        # Processa com o Gemini
        data = await process_medical_document(
            file_bytes=bytes(file_bytes),
            mime_type=mime_type,
            file_name=file_name,
            user_name=user.first_name or "Usuário"
        )

        doc_type = data.get("doc_type", "receita")
        patient_name = data.get("patient_name") or user.first_name
        doctor_name = data.get("doctor_name")
        doc_date_str = data.get("doc_date")
        summary = data.get("summary", "Documento catalogado com sucesso.")
        medications = data.get("medications", [])

        # Converte data se houver
        parsed_doc_date = None
        if doc_date_str:
            try:
                parsed_doc_date = datetime.strptime(doc_date_str, "%Y-%m-%d").date()
            except Exception:
                pass

        # Salva no banco de dados SQLite
        await add_document_with_medications(
            patient_name=patient_name,
            doc_type=doc_type,
            doctor_name=doctor_name,
            doc_date=parsed_doc_date,
            raw_text=None,
            summary=summary,
            file_id=file_id,
            file_path=local_path_str,
            telegram_chat_id=message.chat_id,
            medications_data=medications,
        )

        # Monta resposta para o usuário
        doc_type_icon = {
            "receita": "💊",
            "exame": "🔬",
            "dieta": "🥗",
            "laudo": "📋",
            "atestado": "📄"
        }.get(doc_type, "📑")

        reply_text = (
            f"{doc_type_icon} *{doc_type.upper()} CATALOGADA COM SUCESSO!*\n\n"
            f"👤 *Paciente:* {patient_name}\n"
            f"👨‍⚕️ *Profissional:* {doctor_name or 'Não informado'}\n"
        )
        if parsed_doc_date:
            reply_text += f"📅 *Data do Documento:* {parsed_doc_date.strftime('%d/%m/%Y')}\n"

        reply_text += f"\n📝 *Resumo do que identifiquei:*\n{summary}\n"

        if medications:
            reply_text += f"\n💊 *Medicamentos Extraídos ({len(medications)}):*\n"
            for m in medications:
                reply_text += f"• *{m.get('name')}* - {m.get('dosage', '')}\n"
                if m.get('frequency'):
                    reply_text += f"  ↳ Frequência: {m.get('frequency')}\n"
                if m.get('instructions'):
                    reply_text += f"  ↳ Como tomar: {m.get('instructions')}\n"

        reply_text += "\n✅ _Tudo salvo no histórico! Sempre que precisar saber remédios ou recomendações, basta me perguntar._"

        await status_msg.edit_text(reply_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro ao processar arquivo: {e}", exc_info=True)
        await status_msg.edit_text(
            f"⚠️ Ops! Ocorreu um erro ao tentar processar o arquivo: {str(e)}"
        )
