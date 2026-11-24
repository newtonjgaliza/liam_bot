import logging
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from sqlalchemy import select, delete, desc
from src.database import (
    AsyncSessionLocal,
    Appointment,
    Document,
    Medication,
    User,
)
from src.config import TIMEZONE

logger = logging.getLogger(__name__)


async def tool_agendar_consulta(
    medico: Optional[str] = None,
    data: str = "",
    paciente: Optional[str] = None,
    horario: Optional[str] = None,
    especialidade: Optional[str] = None,
    local: Optional[str] = None,
    observacoes: Optional[str] = None,
    telegram_chat_id: int = 0,
) -> Dict[str, Any]:
    """
    Agenda uma nova consulta médica ou exame no banco de dados e ativa os lembretes automáticos.
    :param medico: Nome do médico, clínica ou tipo de exame
    :param data: Data no formato YYYY-MM-DD
    :param paciente: Nome do paciente (se não informado, assume Geral)
    :param horario: Horário no formato HH:MM (opcional)
    :param especialidade: Especialidade médica ou tipo de procedimento (ex: Exame de esteira)
    :param local: Endereço, clínica ou hospital
    :param observacoes: Observações ou preparos
    """
    try:
        parsed_date = datetime.strptime(data, "%Y-%m-%d").date()
    except Exception:
        return {"status": "erro", "mensagem": f"Formato de data inválido: {data}. Deve ser YYYY-MM-DD."}

    parsed_time = None
    if horario:
        try:
            parsed_time = datetime.strptime(horario, "%H:%M").time()
        except Exception:
            pass

    nome_profissional = medico or especialidade or "Exame/Consulta"

    async with AsyncSessionLocal() as session:
        apt = Appointment(
            patient_name=paciente or "Geral",
            doctor_name=nome_profissional,
            specialty=especialidade,
            appointment_date=parsed_date,
            appointment_time=parsed_time,
            location=local,
            notes=observacoes,
            telegram_chat_id=telegram_chat_id,
        )
        session.add(apt)
        await session.commit()
        await session.refresh(apt)

        return {
            "status": "sucesso",
            "mensagem": f"Consulta com {medico} agendada com sucesso para {parsed_date.strftime('%d/%m/%Y')}!",
            "id_consulta": apt.id,
            "paciente": apt.patient_name,
            "medico": apt.doctor_name,
            "data": parsed_date.strftime("%d/%m/%Y"),
            "horario": parsed_time.strftime("%H:%M") if parsed_time else "Não especificado"
        }


async def tool_listar_consultas(
    paciente: Optional[str] = None,
    medico: Optional[str] = None,
    a_partir_de_hoje: bool = True
) -> List[Dict[str, Any]]:
    """
    Lista consultas agendadas no sistema.
    :param paciente: Filtra por nome do paciente se informado
    :param medico: Filtra por nome do médico se informado
    :param a_partir_de_hoje: Se True, traz apenas consultas futuras
    """
    now = datetime.now(TIMEZONE)
    today = now.date()

    async with AsyncSessionLocal() as session:
        stmt = select(Appointment)
        if a_partir_de_hoje:
            stmt = stmt.where(Appointment.appointment_date >= today)
        stmt = stmt.order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc())

        result = await session.execute(stmt)
        appointments = result.scalars().all()

        output = []
        for apt in appointments:
            if paciente and paciente.lower() not in apt.patient_name.lower():
                continue
            if medico and medico.lower() not in apt.doctor_name.lower():
                continue

            output.append({
                "id": apt.id,
                "paciente": apt.patient_name,
                "medico": apt.doctor_name,
                "especialidade": apt.specialty,
                "data": apt.appointment_date.strftime("%d/%m/%Y"),
                "horario": apt.appointment_time.strftime("%H:%M") if apt.appointment_time else "Sem horário",
                "local": apt.location,
                "observacoes": apt.notes,
            })

        return output


async def tool_buscar_historico_medico(
    termo_busca: Optional[str] = None,
    medico: Optional[str] = None,
    paciente: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pesquisa no histórico por receitas, medicamentos passados, dietas e exames.
    :param termo_busca: Nome do remédio, sintoma, exame ou tipo de dieta
    :param medico: Nome do médico que atendeu ou receitou
    :param paciente: Nome do paciente (se aplicável)
    """
    async with AsyncSessionLocal() as session:
        # Busca remédios
        stmt_meds = select(Medication).order_by(desc(Medication.created_at)).limit(30)
        res_meds = await session.execute(stmt_meds)
        meds = res_meds.scalars().all()

        # Busca documentos
        stmt_docs = select(Document).order_by(desc(Document.created_at)).limit(20)
        res_docs = await session.execute(stmt_docs)
        docs = res_docs.scalars().all()

        filtered_meds = []
        for m in meds:
            match = True
            if termo_busca:
                tb = termo_busca.lower()
                if (tb not in m.name.lower() and
                    (not m.instructions or tb not in m.instructions.lower())):
                    match = False
            if medico and m.doctor_name and medico.lower() not in m.doctor_name.lower():
                match = False
            if paciente and paciente.lower() not in m.patient_name.lower():
                match = False

            if match:
                filtered_meds.append({
                    "medicamento": m.name,
                    "dosagem": m.dosage,
                    "frequencia": m.frequency,
                    "instrucoes": m.instructions,
                    "medico": m.doctor_name,
                    "paciente": m.patient_name,
                    "data": m.prescription_date.strftime("%d/%m/%Y") if m.prescription_date else None,
                })

        filtered_docs = []
        for d in docs:
            match = True
            if termo_busca:
                tb = termo_busca.lower()
                if (tb not in d.summary.lower() and
                    tb not in d.doc_type.lower()):
                    match = False
            if medico and d.doctor_name and medico.lower() not in d.doctor_name.lower():
                match = False
            if paciente and paciente.lower() not in d.patient_name.lower():
                match = False

            if match:
                filtered_docs.append({
                    "tipo": d.doc_type,
                    "paciente": d.patient_name,
                    "medico": d.doctor_name,
                    "data": d.doc_date.strftime("%d/%m/%Y") if d.doc_date else None,
                    "resumo": d.summary,
                })

        return {
            "medicamentos_encontrados": filtered_meds,
            "documentos_encontrados": filtered_docs,
        }


async def tool_cancelar_consulta(id_consulta: int) -> Dict[str, Any]:
    """
    Cancela e remove uma consulta agendada pelo ID.
    :param id_consulta: ID numérico da consulta
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Appointment).where(Appointment.id == id_consulta)
        res = await session.execute(stmt)
        apt = res.scalar_one_or_none()

        if not apt:
            return {"status": "erro", "mensagem": f"Consulta com ID {id_consulta} não foi encontrada."}

        medico = apt.doctor_name
        data_str = apt.appointment_date.strftime("%d/%m/%Y")

        await session.delete(apt)
        await session.commit()

        return {
            "status": "sucesso",
            "mensagem": f"Consulta com {medico} do dia {data_str} foi cancelada com sucesso!"
        }
