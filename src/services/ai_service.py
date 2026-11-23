import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from src.config import GEMINI_API_KEY, TIMEZONE

logger = logging.getLogger(__name__)

# Tenta carregar o SDK moderno do Gemini (google-genai)
try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.warning("google-genai não está instalado ou falhou ao importar.")


def get_gemini_client():
    if not _GENAI_AVAILABLE or not GEMINI_API_KEY:
        return None
    return genai.Client(api_key=GEMINI_API_KEY)


async def analyze_message_intent(message_text: str, user_name: str) -> Dict[str, Any]:
    """
    Analisa a mensagem de texto do usuário para descobrir a intenção:
    - Agendar consulta (INTENT_APPOINTMENT)
    - Pergunta sobre histórico médico/remédios/dietas (INTENT_QUERY)
    - Conversa geral / outros (INTENT_CHAT)
    """
    client = get_gemini_client()
    now = datetime.now(TIMEZONE)
    current_date_str = now.strftime("%Y-%m-%d (%A)")
    current_year = now.year

    if not client:
        # Se a chave de API não foi configurada ainda, faz um fallback básico
        lower = message_text.lower()
        if any(w in lower for w in ["consulta", "médico", "medico", "doutor", "dra", "dr.", "marcar", "agendar"]):
            return {
                "intent": "INTENT_CHAT",
                "reply": "Recebi sua mensagem sobre médico/consulta! Para que eu possa entender datas e extrair os detalhes automaticamente, lembre-se de configurar a `GEMINI_API_KEY` no arquivo `.env`."
            }
        return {
            "intent": "INTENT_CHAT",
            "reply": "Olá! Eu sou o Liam. Para ativar minha inteligência completa de leitura de receitas e consultas, configure a `GEMINI_API_KEY`."
        }

    prompt = f"""
Você é o Liam, o assistente médico e de saúde pessoal de um casal carinhoso.
Data atual de referência: {current_date_str}, ano {current_year}.
Nome do usuário que enviou a mensagem: {user_name}.

Analise a mensagem a seguir do usuário:
"{message_text}"

Classifique a intenção do usuário em UMA das 3 categorias:
1. "APPOINTMENT": O usuário está informando ou pedindo para anotar uma consulta médica, exame, retorno ou dentista.
2. "QUERY": O usuário está fazendo uma pergunta sobre remédios passados, consultas passadas, dietas, laudos ou histórico de saúde (ex: "quais remédios dra flavia passou", "quando é minha consulta", "qual a dieta?").
3. "CHAT": Conversa casual, saudação, agradecimento ou outro assunto.

Retorne SEMPRE em formato JSON estrito, sem crases adicionais ou blocos de código além do JSON puro:
{{
  "intent": "APPOINTMENT" | "QUERY" | "CHAT",
  "appointment_details": {{
      "patient_name": "Nome da pessoa (ex: {user_name}, esposa, etc, ou 'Não especificado')",
      "doctor_name": "Nome do médico/doutor se mencionado ou 'Médico'",
      "specialty": "Especialidade médica (ex: Cardiologista, Dermatologista, Clínico Geral, Dentista)",
      "date": "YYYY-MM-DD (considere o ano atual {current_year} ou próximo ano se o mês já passou)",
      "time": "HH:MM ou null se não informado",
      "location": "Local ou hospital se mencionado ou null",
      "notes": "Observações adicionais ou preparos mencionados"
  }},
  "query_subject": "Resumo do que está sendo perguntado caso seja QUERY",
  "chat_reply": "Resposta acolhedora e direta caso seja CHAT"
}}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        data = json.loads(response.text.strip())
        return data
    except Exception as e:
        logger.error(f"Erro ao analisar intenção com Gemini: {e}")
        return {
            "intent": "CHAT",
            "chat_reply": f"Desculpe, tive um contratempo ao processar sua mensagem: {str(e)}"
        }


async def process_medical_document(
    file_bytes: bytes,
    mime_type: str,
    file_name: str,
    user_name: str
) -> Dict[str, Any]:
    """
    Processa um arquivo enviado (PDF ou imagem de receita, exame ou dieta)
    e extrai estruturadamente as informações médicas.
    """
    client = get_gemini_client()
    now = datetime.now(TIMEZONE)
    current_date_str = now.strftime("%Y-%m-%d")

    if not client:
        return {
            "doc_type": "outro",
            "patient_name": user_name,
            "doctor_name": "Não identificado",
            "doc_date": current_date_str,
            "summary": "Documento recebido e armazenado. (Ative a GEMINI_API_KEY para extração automática)",
            "medications": []
        }

    prompt = f"""
Você é o Liam, assistente especialista em ler e catalogar documentos de saúde (receitas médicas, exames laboratoriais, pedidos médicos, dietas e laudos).
Data atual de referência: {current_date_str}.
Usuário que enviou: {user_name}.

Analise o documento anexado com máxima precisão.
Extraia as seguintes informações em formato JSON estrito:
{{
  "doc_type": "receita" | "exame" | "dieta" | "laudo" | "atestado" | "outro",
  "patient_name": "Nome do paciente identificado no documento (ou '{user_name}' se não encontrado)",
  "doctor_name": "Nome completo do médico/nutricionista com Dr./Dra. se houver",
  "doc_date": "YYYY-MM-DD da data da emissão do documento (ou null se ilegível)",
  "summary": "Resumo claro, organizado e amigável em português dos principais pontos do documento, orientações, datas de retorno ou cuidados",
  "medications": [
    {{
      "name": "Nome do medicamento",
      "dosage": "Dosagem (ex: 50mg, 1 gota/kg, 1 comprimido)",
      "frequency": "Frequência (ex: 8 em 8 horas, 1x ao dia pela manhã)",
      "instructions": "Recomendações de uso (ex: tomar após o almoço, por 7 dias)"
    }}
  ]
}}
"""

    try:
        part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type,
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        data = json.loads(response.text.strip())
        return data
    except Exception as e:
        logger.error(f"Erro ao processar documento com Gemini: {e}")
        return {
            "doc_type": "outro",
            "patient_name": user_name,
            "doctor_name": "Erro na leitura",
            "doc_date": current_date_str,
            "summary": f"Não consegui ler todos os detalhes do arquivo automaticamente. Erro: {str(e)}",
            "medications": []
        }


async def answer_health_query(
    query: str,
    user_name: str,
    recent_documents: List[Any],
    upcoming_appointments: List[Any],
    medications: List[Any]
) -> str:
    """
    Responde perguntas do usuário baseando-se no histórico de documentos,
    remédios cadastrados e consultas agendadas.
    """
    client = get_gemini_client()
    now = datetime.now(TIMEZONE)
    current_date_str = now.strftime("%d/%m/%Y às %H:%M")

    if not client:
        return "Para responder com base no seu histórico médico, preciso que configure a `GEMINI_API_KEY` no arquivo `.env`."

    # Prepara o contexto
    docs_context = []
    for d in recent_documents:
        docs_context.append(
            f"- Tipo: {d.doc_type.upper()} | Paciente: {d.patient_name} | Médico: {d.doctor_name or 'N/I'} | Data: {d.doc_date}\n  Resumo: {d.summary}"
        )

    meds_context = []
    for m in medications:
        meds_context.append(
            f"- Remédio: {m.name} | Paciente: {m.patient_name} | Médico: {m.doctor_name or 'N/I'} | Data: {m.prescription_date}\n  Dose: {m.dosage or 'N/I'} | Frequência: {m.frequency or 'N/I'} | Instruções: {m.instructions or 'N/I'}"
        )

    apts_context = []
    for a in upcoming_appointments:
        time_str = a.appointment_time.strftime("%H:%M") if a.appointment_time else "Horário a confirmar"
        apts_context.append(
            f"- Consulta com {a.doctor_name} ({a.specialty or 'Especialidade n/i'}) para {a.patient_name} em {a.appointment_date.strftime('%d/%m/%Y')} às {time_str}. Obs: {a.notes or 'Nenhuma'}"
        )

    context_str = f"""
=== CONSULTAS REGISTRADAS ===
{chr(10).join(apts_context) if apts_context else "Nenhuma consulta futura registrada."}

=== MEDICAMENTOS RECEITADOS NO HISTÓRICO ===
{chr(10).join(meds_context) if meds_context else "Nenhum medicamento registrado ainda."}

=== DOCUMENTOS E RECEITAS CADASTRADAS ===
{chr(10).join(docs_context) if docs_context else "Nenhum documento salvo ainda."}
"""

    prompt = f"""
Você é o Liam, o assistente médico atencioso e dedicado da família.
Momento atual: {current_date_str}.
Quem está perguntando: {user_name}.

Pergunta do usuário:
"{query}"

Abaixo está o histórico médico real cadastrado no seu banco de dados:
{context_str}

Instruções para responder:
1. Responda de forma clara, amigável, precisa e empática, citando médicos, datas e dosagens quando disponíveis no histórico.
2. Diferencie claramente se a informação é do usuário ou da esposa dele quando houver essa indicação.
3. Se a informação não constar nos dados acima, seja sincero e informe educadamente que não encontrou aquele registro ou receita no histórico cadastrado até o momento.
4. Lembre-se: você é um assistente de organização de saúde e não substitui uma avaliação médica direta.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Erro ao responder pergunta médica: {e}")
        return f"Tive uma falha ao consultar os registros: {str(e)}"
