import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from src.config import GEMINI_API_KEY, GEMINI_MODEL, TIMEZONE
from src.services.tools import (
    tool_agendar_consulta,
    tool_listar_consultas,
    tool_buscar_historico_medico,
    tool_cancelar_consulta,
)

logger = logging.getLogger(__name__)

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


# Definição das Tools (Ferramentas) para o Gemini
LIAM_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="agendar_consulta",
                description="Agenda uma nova consulta médica, retorno ou exame no banco de dados para ativar os lembretes automáticos.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "medico": types.Schema(type=types.Type.STRING, description="Nome do médico, dentista ou profissional de saúde (ex: Dra. Flávia)"),
                        "data": types.Schema(type=types.Type.STRING, description="Data da consulta no formato estrito YYYY-MM-DD"),
                        "paciente": types.Schema(type=types.Type.STRING, description="Nome do paciente (se não especificado, deixar vazio ou 'Geral')"),
                        "horario": types.Schema(type=types.Type.STRING, description="Horário no formato HH:MM (ex: 14:30), ou null se não informado"),
                        "especialidade": types.Schema(type=types.Type.STRING, description="Especialidade médica (ex: Cardiologista, Nutricionista, Pediatra)"),
                        "local": types.Schema(type=types.Type.STRING, description="Local da consulta, hospital ou consultório"),
                        "observacoes": types.Schema(type=types.Type.STRING, description="Observações, recomendações de jejum ou preparo"),
                    },
                    required=["medico", "data"],
                ),
            ),
            types.FunctionDeclaration(
                name="listar_consultas",
                description="Consulta a lista de consultas e exames agendados no sistema.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "paciente": types.Schema(type=types.Type.STRING, description="Filtra por nome do paciente se solicitado"),
                        "medico": types.Schema(type=types.Type.STRING, description="Filtra por nome do médico se solicitado"),
                        "a_partir_de_hoje": types.Schema(type=types.Type.BOOLEAN, description="Se True, busca consultas a partir de hoje. Padrão True"),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="buscar_historico_medico",
                description="Pesquisa no histórico por receitas, medicamentos passados, dosagens, frequências, dietas e exames.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "termo_busca": types.Schema(type=types.Type.STRING, description="Nome do remédio, sintoma, orientação ou tipo de dieta"),
                        "medico": types.Schema(type=types.Type.STRING, description="Nome do médico que passou a receita ou consulta"),
                        "paciente": types.Schema(type=types.Type.STRING, description="Nome do paciente"),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="cancelar_consulta",
                description="Cancela uma consulta agendada pelo seu ID numérico.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_consulta": types.Schema(type=types.Type.INTEGER, description="ID numérico da consulta a ser cancelada"),
                    },
                    required=["id_consulta"],
                ),
            ),
        ]
    )
]


async def execute_tool_call(call: Any, telegram_chat_id: int) -> Dict[str, Any]:
    """Executa a função correspondente à chamada da Tool do modelo."""
    fn_name = call.name
    fn_args = call.args or {}

    logger.info(f"🛠️ Executando Tool: {fn_name} com argumentos: {fn_args}")

    if fn_name == "agendar_consulta":
        return await tool_agendar_consulta(
            medico=fn_args.get("medico", "Médico"),
            data=fn_args.get("data"),
            paciente=fn_args.get("paciente"),
            horario=fn_args.get("horario"),
            especialidade=fn_args.get("especialidade"),
            local=fn_args.get("local"),
            observacoes=fn_args.get("observacoes"),
            telegram_chat_id=telegram_chat_id,
        )
    elif fn_name == "listar_consultas":
        return {
            "consultas": await tool_listar_consultas(
                paciente=fn_args.get("paciente"),
                medico=fn_args.get("medico"),
                a_partir_de_hoje=fn_args.get("a_partir_de_hoje", True),
            )
        }
    elif fn_name == "buscar_historico_medico":
        return await tool_buscar_historico_medico(
            termo_busca=fn_args.get("termo_busca"),
            medico=fn_args.get("medico"),
            paciente=fn_args.get("paciente"),
        )
    elif fn_name == "cancelar_consulta":
        return await tool_cancelar_consulta(
            id_consulta=int(fn_args.get("id_consulta"))
        )

    return {"erro": f"Ferramenta {fn_name} não encontrada."}


async def chat_with_agent(
    user_message: str,
    user_name: str,
    telegram_chat_id: int,
) -> str:
    """
    Agente completo do Liam:
    Processa a mensagem com acesso a Tools para consultar, agendar e pesquisar no histórico.
    """
    client = get_gemini_client()
    now = datetime.now(TIMEZONE)
    current_date_str = now.strftime("%Y-%m-%d (%A, %d de %B de %Y)")
    current_time_str = now.strftime("%H:%M")
    current_year = now.year

    if not client:
        return (
            "Olá! Eu sou o Liam. Para que eu possa usar minhas ferramentas de agendamento e memória, "
            "certifique-se de configurar a `GEMINI_API_KEY` no arquivo `.env`."
        )

    system_instruction = f"""
Você é o Liam, o assistente médico e de saúde pessoal de um casal carinhoso.
Você tem acesso a FERRAMENTAS (Tools) para gerenciar consultas e consultar o histórico de receitas e dietas.

Informações temporais de referência:
- Data atual: {current_date_str}
- Horário atual: {current_time_str}
- Ano atual: {current_year}
- Usuário que está falando agora: {user_name}

COMO VOCÊ DEVE AGIR:
1. Sempre que o usuário mencionar uma consulta (marcar, agendar, avisar que tem consulta dia X), use a tool `agendar_consulta`.
   - Se o usuário disser apenas o dia e o mês (ex: "dia 12 de dezembro"), deduza o ano correto considerando o momento atual ({current_year} ou próximo ano se o mês já passou).
   - Se o horário não foi falado, deixe o campo de horário como null ou pergunte com carinho depois de agendar.
   - Sempre avise que os lembretes automáticos estão ativados (na véspera, no dia pela manhã e 2h antes).
2. Sempre que perguntarem sobre remédios, receitas passadas, dietas ou recomendações médicas (ex: "quais remédios dra flavia passou", "o que a nutricionista disse"), use a tool `buscar_historico_medico`.
3. Sempre que perguntarem sobre compromissos ou consultas futuras ("quando é minha consulta", "quais consultas temos esse mês"), use a tool `listar_consultas`.
4. Seja sempre atencioso, empático, claro e fale em português com formatação limpa (use negrito e emojis quando apropriado).
"""

    messages = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)]
        )
    ]

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=LIAM_TOOLS,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    try:
        # 1ª Rodada assíncrona: Modelo decide se responde direto ou chama ferramentas
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=messages,
            config=config,
        )

        # Loop de execução de Tools (quando o modelo aciona funções)
        max_tool_rounds = 4
        current_round = 0

        while response.function_calls and current_round < max_tool_rounds:
            current_round += 1
            tool_responses = []

            # Adiciona a resposta com as chamadas de função ao histórico
            messages.append(response.candidates[0].content)

            for call in response.function_calls:
                tool_result = await execute_tool_call(call, telegram_chat_id)
                tool_responses.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response={"result": tool_result}
                    )
                )

            # Envia o resultado das tools de volta com role="tool"
            messages.append(types.Content(role="tool", parts=tool_responses))

            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=messages,
                config=config,
            )

        return response.text or "Entendido! Processamento concluído."

    except Exception as e:
        logger.error(f"Erro no agente Liam: {e}", exc_info=True)
        return f"Desculpe, tive um imprevisto ao processar: {str(e)}"


async def process_medical_document(
    file_bytes: bytes,
    mime_type: str,
    file_name: str,
    user_name: str,
    user_caption: str = "",
    extracted_text: str = "",
) -> Dict[str, Any]:
    """
    Processa um arquivo enviado (PDF completo, foto de receita manuscrita/impressa,
    foto de caixa de remédio, dieta ou pedido de exame) e extrai estruturadamente as informações médicas.
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
            "summary": "Documento recebido e armazenado. Configure a GEMINI_API_KEY para extração completa.",
            "medications": []
        }

    caption_context = f"\nLegenda/Comentário enviado pelo usuário junto com o arquivo: '{user_caption}'" if user_caption else ""
    text_context = f"\nTexto pré-extraído do PDF digital:\n{extracted_text[:3000]}" if extracted_text else ""

    prompt = f"""
Você é o Liam, o assistente médico especialista em visão computacional e leitura minuciosa de documentos de saúde da família.
Você deve ser capaz de ler e interpretar com extrema precisão:
1. Arquivos em PDF de receitas médicas, atestados, planos alimentares (dietas) e laudos de exames laboratoriais.
2. Fotos de receitas (mesmo com letra manuscrita de médico difícil de ler ou carimbo médico).
3. Fotos de caixas/embalagens de remédios, cartelas, bulas ou fotos de mensagens com indicação de remédios.

Data atual de referência: {current_date_str}.
Usuário que enviou o arquivo: {user_name}.{caption_context}{text_context}

Analise a imagem/documento anexado com máxima dedicação.
Extraia as seguintes informações e retorne SEMPRE em formato JSON estrito:
{{
  "doc_type": "receita" | "exame" | "dieta" | "laudo" | "atestado" | "foto_remedio" | "indicacao" | "outro",
  "patient_name": "Nome da pessoa a quem o documento ou remédio se destina (identifique no documento ou na legenda se é {user_name} ou esposa; caso não conste, use '{user_name}')",
  "doctor_name": "Nome completo do médico/nutricionista/profissional com título (ex: Dra. Flávia) ou 'Não informado'",
  "doc_date": "YYYY-MM-DD da data da prescrição/exame (se ilegível ou for apenas foto de remédio, use '{current_date_str}')",
  "summary": "Resumo completo, acolhedor e muito claro em português do que se trata o documento/foto, para que serve o remédio identificado, horários e orientações principais",
  "medications": [
    {{
      "name": "Nome comercial ou princípio ativo do medicamento ou suplemento",
      "dosage": "Dosagem ou concentração (ex: 50mg, 1 comprimido, 20 gotas, 1 scoop)",
      "frequency": "Frequência de uso (ex: 8 em 8 horas, 1x ao dia pela manhã, de 12 em 12h após as refeições)",
      "instructions": "Como usar, tempo de tratamento ou recomendações especiais (ex: tomar com água em jejum, por 14 dias)"
    }}
  ]
}}
"""

    try:
        part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type,
        )
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
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
