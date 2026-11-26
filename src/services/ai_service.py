import asyncio
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
    tool_consultar_restricoes_alimentares,
    tool_atualizar_restricoes_alimentares,
    tool_verificar_compatibilidade_alimento,
)
from src.database import (
    get_dietary_profile,
    add_food_check,
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
                description="Agenda uma nova consulta médica, exame ou retorno no banco de dados para ativar os lembretes automáticos.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "medico": types.Schema(type=types.Type.STRING, description="Nome do médico, dentista, clínica ou tipo de exame (ex: Dra. Flávia, Ecomedical, Exame de esteira)"),
                        "data": types.Schema(type=types.Type.STRING, description="Data da consulta ou exame no formato estrito YYYY-MM-DD"),
                        "paciente": types.Schema(type=types.Type.STRING, description="Nome do paciente (se não especificado, deixar vazio ou 'Geral')"),
                        "horario": types.Schema(type=types.Type.STRING, description="Horário no formato HH:MM (ex: 14:15), ou null se não informado"),
                        "especialidade": types.Schema(type=types.Type.STRING, description="Especialidade médica ou procedimento (ex: Exame de esteira, Cardiologia)"),
                        "local": types.Schema(type=types.Type.STRING, description="Local da consulta, hospital ou clínica (ex: Ecomedical)"),
                        "observacoes": types.Schema(type=types.Type.STRING, description="Observações, recomendações de jejum ou preparo"),
                    },
                    required=["data"],
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
            types.FunctionDeclaration(
                name="consultar_restricoes_alimentares",
                description="Consulta o perfil alimentar, alimentos proibidos, moderados e permitidos de Newton ou Janaína.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "paciente": types.Schema(type=types.Type.STRING, description="Nome da pessoa ('Newton' ou 'Janaína'). Se não informado, busca de ambos."),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="atualizar_restricoes_alimentares",
                description="Atualiza ou adiciona restrições alimentares para Newton ou Janaína.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "paciente": types.Schema(type=types.Type.STRING, description="Nome da pessoa ('Newton' ou 'Janaína')"),
                        "proibidos": types.Schema(type=types.Type.STRING, description="Alimentos proibidos (ex: glúten, lactose, frutos do mar)"),
                        "restritos": types.Schema(type=types.Type.STRING, description="Alimentos restritos ou com limites de porção (ex: alho, cebola, feijão)"),
                        "permitidos": types.Schema(type=types.Type.STRING, description="Alimentos liberados e substitutos seguros"),
                        "observacoes": types.Schema(type=types.Type.STRING, description="Metas ou orientações nutricionais"),
                    },
                    required=["paciente"],
                ),
            ),
            types.FunctionDeclaration(
                name="verificar_compatibilidade_alimento",
                description="Verifica se um prato, alimento, ingrediente ou receita é permitido para Newton ou Janaína.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "alimento": types.Schema(type=types.Type.STRING, description="Nome do alimento, receita ou lista de ingredientes"),
                        "paciente": types.Schema(type=types.Type.STRING, description="Para quem é o alimento ('Newton' ou 'Janaína')"),
                    },
                    required=["alimento"],
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
        medico_val = fn_args.get("medico") or fn_args.get("especialidade") or fn_args.get("local") or "Consulta/Exame"
        return await tool_agendar_consulta(
            medico=medico_val,
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
    elif fn_name == "consultar_restricoes_alimentares":
        return await tool_consultar_restricoes_alimentares(
            paciente=fn_args.get("paciente")
        )
    elif fn_name == "atualizar_restricoes_alimentares":
        return await tool_atualizar_restricoes_alimentares(
            paciente=fn_args.get("paciente", "Newton"),
            proibidos=fn_args.get("proibidos"),
            restritos=fn_args.get("restritos"),
            permitidos=fn_args.get("permitidos"),
            observacoes=fn_args.get("observacoes"),
        )
    elif fn_name == "verificar_compatibilidade_alimento":
        return await tool_verificar_compatibilidade_alimento(
            alimento=fn_args.get("alimento", ""),
            paciente=fn_args.get("paciente"),
        )

    return {"erro": f"Ferramenta {fn_name} não encontrada."}


async def generate_content_with_retry(
    client,
    model: str,
    contents: Any,
    config: Any,
    max_retries: int = 3,
) -> Any:
    """
    Executa a chamada assíncrona ao Gemini com retry automático e fallback para modelos estáveis.
    """
    models_to_try = [model, "gemini-2.5-flash", "gemini-1.5-flash"]
    unique_models = list(dict.fromkeys(models_to_try))
    last_err = None

    for m in unique_models:
        for attempt in range(max_retries):
            try:
                return await client.aio.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if attempt < max_retries - 1 and any(k in err_str for k in ["503", "unavailable", "429", "resource_exhausted", "high demand"]):
                    wait_time = (attempt + 1) * 1.5
                    logger.warning(
                        f"⚠️ Google API ocupada (503/429) no modelo {m}. Tentativa {attempt + 1}/{max_retries}. "
                        f"Aguardando {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                logger.warning(f"Falha no modelo {m}: {e}. Tentando alternativa estável...")
                break

    if last_err:
        raise last_err


async def send_chat_message_with_retry(chat, message: Any, max_retries: int = 3) -> Any:
    """Envia mensagem no chat assíncrono com retry automático em caso de 503 temporário."""
    for attempt in range(max_retries):
        try:
            return await chat.send_message(message)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["503", "unavailable", "429", "resource_exhausted", "high demand"]):
                wait_time = (attempt + 1) * 1.5
                logger.warning(
                    f"⚠️ Google API ocupada (503/429). Tentativa {attempt + 1}/{max_retries}. "
                    f"Aguardando {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
                continue
            raise e


async def chat_with_agent(
    user_message: str,
    user_name: str,
    telegram_chat_id: int,
) -> str:
    """
    Agente completo do Liam:
    Processa a mensagem com acesso a Tools para consultar, agendar e pesquisar no histórico
    usando sessões de Chat nativas.
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
Você é o Liam, o assistente médico e de saúde pessoal de um casal carinhoso (Newton e Janaína).
Você tem acesso a FERRAMENTAS (Tools) para gerenciar consultas, exames, consultar o histórico de receitas e gerenciar o perfil de RESTRIÇÕES ALIMENTARES da família.

Informações temporais de referência:
- Data atual: {current_date_str}
- Horário atual: {current_time_str}
- Ano atual: {current_year}
- Usuário que está falando agora: {user_name}

COMO VOCÊ DEVE AGIR:
1. CONSULTAS E EXAMES:
   - Sempre que o usuário mencionar uma consulta ou exame (marcar, agendar, avisar que tem compromisso dia X ou amanhã), use a tool `agendar_consulta`.
   - Se o usuário disser "amanhã", calcule a data de amanhã a partir da data atual ({current_date_str}).
   - Se o usuário disser apenas o dia e o mês (ex: "dia 12 de dezembro"), deduza o ano correto considerando o momento atual ({current_year} ou próximo ano se o mês já passou).
   - Se não houver nome de médico (como em exames laboratoriais, de imagem ou esteira), use o nome do exame ou da clínica.
   - Sempre avise que os lembretes automáticos estão ativados (na véspera, no dia pela manhã e 2h antes).
   - Sempre que perguntarem sobre compromissos ou consultas futuras ("quando é minha consulta", "quais consultas temos esse mês"), use a tool `listar_consultas`.
2. RECEITAS E HISTÓRICO MÉDICO:
   - Sempre que perguntarem sobre remédios, receitas passadas, dosagens ou recomendações médicas passadas (ex: "quais remédios dra flavia passou"), use a tool `buscar_historico_medico`.
3. RESTRIÇÕES ALIMENTARES E DIETA:
   - Newton tem restrições alimentares estritas:
     * Glúten 100% PROIBIDO (sem glúten absoluto: trigo, centeio, cevada, aveia convencional, malte, etc.).
     * Lactose PROIBIDA (apenas sem lactose ou leites vegetais de aveia sem glúten).
     * Quantidades controladas / moderadas: feijão (80g), cebola roxa (30g refogada), alho (1 dente por panela), beterraba (60g), café (2 xícaras/dia), molho de tomate (60g).
   - Janaína tem seu perfil alimentar próprio no sistema.
   - Sempre que perguntarem se Newton ou Janaína podem comer um alimento, ingrediente ou receita ("eu posso comer isso?", "janaina pode comer isso?", "o que eu posso comer?"), use `verificar_compatibilidade_alimento` ou `consultar_restricoes_alimentares`.
   - Sempre que pedirem para alterar ou registrar uma nova restrição da Janaína ou do Newton, use `atualizar_restricoes_alimentares`.
4. Seja sempre atencioso, empático, claro e fale em português com formatação limpa (use negrito e emojis quando apropriado).
"""

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=LIAM_TOOLS,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    models_to_try = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-1.5-flash"]
    unique_models = list(dict.fromkeys(models_to_try))
    last_error = None

    try:
        for model_name in unique_models:
            try:
                # Usa sessão de chat nativa do SDK
                chat = client.aio.chats.create(
                    model=model_name,
                    config=config,
                )

                response = await send_chat_message_with_retry(chat, user_message)

                # Loop de execução de Tools (quando o modelo aciona funções)
                max_tool_rounds = 4
                current_round = 0

                while response.function_calls and current_round < max_tool_rounds:
                    current_round += 1
                    tool_responses = []

                    for call in response.function_calls:
                        tool_result = await execute_tool_call(call, telegram_chat_id)
                        tool_responses.append(
                            types.Part.from_function_response(
                                name=call.name,
                                response={"result": tool_result}
                            )
                        )

                    # Envia as respostas das tools de volta para a sessão do chat
                    response = await send_chat_message_with_retry(chat, tool_responses)

                return response.text or "Entendido! Compromisso anotado com sucesso."

            except Exception as e:
                last_error = e
                logger.warning(f"Tentativa com modelo {model_name} falhou: {e}. Tentando alternativa...")
                continue

        if last_error:
            raise last_error

    except Exception as e:
        logger.error(f"Erro no agente Liam: {e}", exc_info=True)
        err_msg = str(e)
        if any(k in err_msg.lower() for k in ["503", "unavailable", "high demand"]):
            return "Os servidores da Google estão com alta demanda temporária neste instante. Por favor, tente enviar sua mensagem novamente em alguns segundos! 😊"
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
        response = await generate_content_with_retry(
            client=client,
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


# ==============================================================
# ANÁLISE MULTIMODAL DE INGREDIENTES E RÓTULOS (VISÃO COMPUTACIONAL)
# ==============================================================

def resolve_target_patient(caption: str, user_name: str) -> str:
    """
    Identifica de forma inteligente para quem é a pergunta (Newton ou Janaína),
    analisando menções na legenda ou o remetente da mensagem.
    """
    cap = (caption or "").lower().strip()
    u_name = (user_name or "").lower()

    # 1. Menção explícita a Janaína
    if any(k in cap for k in ["janaina", "janaína", "jana", "esposa", "mulher", "ela"]):
        return "Janaína"

    # 2. Menção explícita a Newton
    if any(k in cap for k in ["newton", "marido", "ele"]):
        return "Newton"

    # 3. Perguntas em 1ª pessoa ("eu posso comer", "pra mim", "minha dieta")
    if any(k in cap for k in ["eu posso", "posso comer", "posso tomar", "pra mim", "minha dieta", "eu consigo"]):
        if "jana" in u_name:
            return "Janaína"
        return "Newton"

    # 4. Se quem mandou a mensagem for Janaína
    if "jana" in u_name:
        return "Janaína"

    # Padrão: Newton
    return "Newton"


def is_food_check_intent(caption: str) -> bool:
    """Verifica se a legenda enviada com a foto indica intenção de checar alimento/rótulo."""
    if not caption:
        return False
    cap = caption.lower()
    keywords = [
        "comer", "posso", "pode", "ingrediente", "ingredientes",
        "rótulo", "rotulo", "alimento", "alimentos", "comida",
        "dieta", "lanche", "snack", "tabela", "caloria",
        "gluten", "glúten", "lactose", "doce", "bebida",
        "produto", "supermercado", "almoço", "jantar", "café",
        "tomar", "beber", "comprar", "levar", "guloseima",
        "salgado", "sobremesa", "biscoito", "bolacha", "molho"
    ]
    return any(k in cap for k in keywords)


async def analyze_food_photo(
    file_bytes: bytes,
    mime_type: str,
    target_person: str,
    user_caption: str = "",
    user_name: str = "Usuário",
    telegram_chat_id: int = 0,
) -> Dict[str, Any]:
    """
    Analisa a foto de uma embalagem/rótulo de alimento e lista de ingredientes
    confrontando minuciosamente com o perfil alimentar da pessoa (Newton ou Janaína).
    """
    client = get_gemini_client()
    profile = await get_dietary_profile(target_person)

    prohibited_info = profile.prohibited_items if profile else "Glúten e lactose proibidos."
    restricted_info = profile.restricted_items if profile else "Alho e cebola moderados."
    allowed_info = profile.allowed_items if profile else "Alimentos sem glúten e sem lactose."
    notes_info = profile.notes if profile else ""

    if not client:
        return {
            "is_food_label": True,
            "product_name": "Alimento da Foto",
            "target_person": target_person,
            "status": "ATENCAO",
            "headline": "⚠️ GEMINI NÃO CONFIGURADO",
            "prohibited_found": [],
            "restricted_found": [],
            "safe_ingredients": [],
            "allergens_warning": "",
            "verdict_explanation": "A chave GEMINI_API_KEY precisa estar configurada no arquivo .env para análise de visão.",
            "recommendation": "Configure a chave de API para habilitar a análise de ingredientes."
        }

    prompt = f"""
Você é o Liam, o assistente médico e nutricional especialista em visão computacional, leitura minuciosa de rótulos de alimentos e segurança alimentar.
Você está prestando consultoria imediata para {target_person.upper()} no supermercado ou em casa.

PERFIL ALIMENTAR E RESTRIÇÕES DE {target_person.upper()}:
- 🚫 PROIBIÇÃO ABSOLUTA: {prohibited_info}
- ⚠️ ATENÇÃO / CONSUMO EM QUANTIDADE CONTROLADA: {restricted_info}
- 🟢 ALIMENTOS E TROCAS LIBERADAS: {allowed_info}
- 📋 OBSERVAÇÕES E METAS: {notes_info}

Legenda ou pergunta enviada pelo usuário: "{user_caption}"
Usuário que enviou a foto: {user_name}

DIRETRIZES DE LEITURA E ANÁLISE:
1. Inspecione com máximo zoom e atenção o texto impresso no rótulo, especialmente a seção "Ingredientes:", tabela nutricional e alertas de "ALÉRGICOS:".
2. Se a imagem NÃO for de um alimento, embalagem, lista de ingredientes ou produto comestível (por exemplo: for uma receita médica, pedido de exame laboratorial, caixa de medicamento farmacêutico):
   Defina "is_food_label": false.
3. Se FOR um alimento ou rótulo:
   Defina "is_food_label": true.
   Analise com rigor cada ingrediente identificado:
   - GLÚTEN OCULTO: trigo, farinha de trigo, farelo de trigo, centeio, cevada, aveia convencional (sem selo sem glúten explícito), malte, extrato de malte, xarope de malte, aroma de malte, farinha de rosca, levedura de cerveja.
   - LACTOSE / LEITE: leite integral/desnatado, leite em pó, soro de leite, soro de leite em pó, permeado de soro, caseína, caseinato, queijo com lactose, creme de leite comum, manteiga, gordura anidra de leite.
   - CONDIMENTOS / RESTRIÇÕES FODMAP DE {target_person.upper()}: alho em pó, cebola em pó, excesso de feijão ou beterraba concentrados, caldos prontos.
4. Classifique o status em:
   - "LIBERADO": Não contém nenhum ingrediente proibido ou restrito. Totalmente seguro para {target_person}.
   - "ATENCAO": Não contém proibidos absolutos, mas contém ingredientes que requerem moderação (ex: alho/cebola em pequenas doses, ou aviso de 'pode conter traços' de contaminação cruzada).
   - "PROIBIDO": Contém ingredientes proibidos para {target_person} (ex: glúten ou lactose para o Newton).
   - "NAO_IDENTIFICADO": A foto está muito borrada, cortada ou a lista de ingredientes não está legível.

Retorne SEMPRE em formato JSON estrito:
{{
  "is_food_label": true,
  "product_name": "Nome da marca/produto identificado ou 'Produto alimentício'",
  "target_person": "{target_person}",
  "status": "LIBERADO" | "ATENCAO" | "PROIBIDO" | "NAO_IDENTIFICADO",
  "headline": "Frase de efeito curta para o veredito",
  "prohibited_found": ["lista de ingredientes proibidos encontrados"],
  "restricted_found": ["lista de ingredientes com limite ou atenção"],
  "safe_ingredients": ["principais ingredientes seguros identificados"],
  "allergens_warning": "Texto de alérgicos do rótulo se houver, ou vazio",
  "verdict_explanation": "Explicação clínica, clara e acolhedora em português do porquê pode ou não pode comer",
  "recommendation": "Orientação prática do que fazer (ex: Pode comer com tranquilidade! / Evite comprar este produto! / Coma no máximo 1 porção pequena)"
}}
"""

    try:
        part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type,
        )
        response = await generate_content_with_retry(
            client=client,
            model=GEMINI_MODEL,
            contents=[part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        data = json.loads(response.text.strip())

        # Registra a checagem no banco de dados se for alimento
        if data.get("is_food_label", True):
            try:
                identified = ", ".join(data.get("prohibited_found", []) + data.get("restricted_found", []))
                await add_food_check(
                    patient_name=target_person,
                    product_name=data.get("product_name", "Alimento"),
                    status=data.get("status", "ATENCAO"),
                    summary=data.get("verdict_explanation", ""),
                    identified_ingredients=identified if identified else None,
                    telegram_chat_id=telegram_chat_id,
                )
            except Exception as db_err:
                logger.warning(f"Não foi possível salvar food_check no banco: {db_err}")

        return data
    except Exception as e:
        logger.error(f"Erro ao analisar foto de alimento com Gemini: {e}")
        return {
            "is_food_label": True,
            "product_name": "Alimento",
            "target_person": target_person,
            "status": "NAO_IDENTIFICADO",
            "headline": "⚠️ DIFICULDADE NA LEITURA",
            "prohibited_found": [],
            "restricted_found": [],
            "safe_ingredients": [],
            "allergens_warning": "",
            "verdict_explanation": f"Não consegui ler os ingredientes com clareza. Erro: {str(e)}",
            "recommendation": "Tente tirar uma foto mais aproximada e focada na lista de ingredientes da embalagem."
        }


def format_food_analysis_telegram(data: Dict[str, Any], target_person: str) -> str:
    """Formata o resultado da análise de ingredientes em uma mensagem bonita e clara para o Telegram."""
    status = data.get("status", "ATENCAO")
    product = data.get("product_name", "Alimento")
    explanation = data.get("verdict_explanation", "")
    prohibited = data.get("prohibited_found", [])
    restricted = data.get("restricted_found", [])
    recommendation = data.get("recommendation", "")
    allergens = data.get("allergens_warning", "")

    if status == "LIBERADO":
        icon = "🟢"
        header = f"{icon} *LIBERADO PARA {target_person.upper()}!*"
    elif status == "PROIBIDO":
        icon = "🔴"
        header = f"{icon} *NÃO RECOMENDADO / PROIBIDO PARA {target_person.upper()}!*"
    elif status == "ATENCAO":
        icon = "🟡"
        header = f"{icon} *ATENÇÃO À QUANTIDADE PARA {target_person.upper()}!*"
    else:
        icon = "⚠️"
        header = f"{icon} *NÃO FOI POSSÍVEL CONFIRMAR OS INGREDIENTES*"

    lines = [header, ""]
    if product and product.lower() not in ["alimento", "produto alimentício", "produto"]:
        lines.append(f"📦 *Produto:* {product}")
    lines.append(f"👤 *Avaliado para:* {target_person}")
    lines.append("")

    if prohibited:
        lines.append("🚫 *Ingredientes Proibidos Encontrados:*")
        for item in prohibited:
            lines.append(f"• *{item}*")
        lines.append("")

    if restricted:
        lines.append("⚠️ *Ingredientes com Restrição de Dose / Moderação:*")
        for item in restricted:
            lines.append(f"• {item}")
        lines.append("")

    if explanation:
        lines.append(f"📋 *Avaliação:* {explanation}")
        lines.append("")

    if recommendation:
        lines.append(f"💡 *Orientação do Liam:* {recommendation}")
        lines.append("")

    if allergens:
        lines.append(f"ℹ️ *Alerta de Alérgenos no Rótulo:* _{allergens}_")

    return "\n".join(lines).strip()

