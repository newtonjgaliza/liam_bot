import io
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
import pypdf
from src.handlers.auth import check_auth
from src.services.ai_service import process_medical_document
from src.database import add_document_with_medications, get_or_create_user
from src.config import UPLOADS_DIR

logger = logging.getLogger(__name__)


def extract_pdf_text_fallback(pdf_bytes: bytes) -> str:
    """Tenta extrair o texto embutido do PDF via pypdf caso exista camada de texto."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                texts.append(f"--- Página {i+1} ---\n{text.strip()}")
        return "\n\n".join(texts)
    except Exception as e:
        logger.warning(f"Não foi possível extrair texto digital do PDF via pypdf: {e}")
        return ""


async def handle_document_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processa documentos (PDFs) e fotos de receitas, dietas, caixas de remédios ou exames.
    """
    if not check_auth(update):
        return

    message = update.message
    user = update.effective_user
    await get_or_create_user(user.id, user.first_name)

    caption = message.caption or ""
    file_obj = None
    file_name = "arquivo"
    mime_type = "application/pdf"

    status_msg = await message.reply_text("📥 Recebi seu arquivo! Liam está lendo e analisando cada detalhe...")

    try:
        if message.document:
            file_obj = await message.document.get_file()
            file_name = message.document.file_name or "documento.pdf"
            mime_type = message.document.mime_type or "application/pdf"
            file_id = message.document.file_id

            # Ajuste de mime_type caso venha genérico
            lower_name = file_name.lower()
            if lower_name.endswith(".pdf"):
                mime_type = "application/pdf"
            elif lower_name.endswith((".jpg", ".jpeg")):
                mime_type = "image/jpeg"
            elif lower_name.endswith(".png"):
                mime_type = "image/png"
            elif lower_name.endswith(".webp"):
                mime_type = "image/webp"

        elif message.photo:
            # Pega a foto com maior resolução enviada
            photo = message.photo[-1]
            file_obj = await photo.get_file()
            file_name = f"foto_{photo.file_unique_id}.jpg"
            mime_type = "image/jpeg"
            file_id = photo.file_id
        else:
            await status_msg.edit_text("Formato não suportado. Por favor, envie um PDF ou foto da receita/remédio/exame.")
            return

        # Baixa os bytes do arquivo enviado
        file_bytes = await file_obj.download_as_bytearray()
        bytes_data = bytes(file_bytes)

        # Se for PDF, tenta extrair o texto digital prévio
        raw_pdf_text = ""
        if mime_type == "application/pdf":
            raw_pdf_text = extract_pdf_text_fallback(bytes_data)

        # Salva cópia local segura no diretório uploads
        local_path = UPLOADS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"
        try:
            with open(local_path, "wb") as f:
                f.write(bytes_data)
            local_path_str = str(local_path)
        except Exception:
            local_path_str = None

        # Processa via IA Multimodal (Gemini lê tanto PDF nativo quanto fotos de caixas ou receitas)
        data = await process_medical_document(
            file_bytes=bytes_data,
            mime_type=mime_type,
            file_name=file_name,
            user_name=user.first_name or "Usuário",
            user_caption=caption,
            extracted_text=raw_pdf_text,
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
            raw_text=raw_pdf_text if raw_pdf_text else None,
            summary=summary,
            file_id=file_id,
            file_path=local_path_str,
            telegram_chat_id=message.chat_id,
            medications_data=medications,
        )

        # Monta resposta visual amigável para o usuário
        doc_type_icon = {
            "receita": "💊",
            "exame": "🔬",
            "dieta": "🥗",
            "laudo": "📋",
            "atestado": "📄",
            "indicacao": "💡",
            "foto_remedio": "📦"
        }.get(doc_type, "📑")

        reply_text = (
            f"{doc_type_icon} *{doc_type.upper()} CATALOGADA COM SUCESSO!*\n\n"
            f"👤 *Paciente:* {patient_name}\n"
        )
        if doctor_name and doctor_name.lower() not in ["não identificado", "não informado", "erro na leitura"]:
            reply_text += f"👨‍⚕️ *Profissional:* {doctor_name}\n"

        if parsed_doc_date:
            reply_text += f"📅 *Data:* {parsed_doc_date.strftime('%d/%m/%Y')}\n"

        reply_text += f"\n📝 *O que identifiquei:*\n{summary}\n"

        if medications:
            reply_text += f"\n💊 *Medicamentos / Itens Extraídos ({len(medications)}):*\n"
            for m in medications:
                reply_text += f"• *{m.get('name')}*"
                if m.get('dosage'):
                    reply_text += f" ({m.get('dosage')})"
                reply_text += "\n"
                if m.get('frequency'):
                    reply_text += f"  ↳ *Frequência:* {m.get('frequency')}\n"
                if m.get('instructions'):
                    reply_text += f"  ↳ *Instruções:* {m.get('instructions')}\n"

        reply_text += (
            "\n✅ _Tudo salvo no histórico! Sempre que precisar lembrar o que tomar ou a dosagem, "
            "basta me perguntar!_"
        )

        await status_msg.edit_text(reply_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro ao processar arquivo: {e}", exc_info=True)
        await status_msg.edit_text(
            f"⚠️ Ops! Ocorreu um erro ao tentar processar o arquivo: {str(e)}"
        )
