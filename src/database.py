from datetime import datetime, date, time
from typing import List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Text,
    Date,
    Time,
    DateTime,
    Boolean,
    ForeignKey,
    select,
    desc,
)
from src.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="Usuário")
    patient_alias: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_name: Mapped[str] = mapped_column(String(100), default="Geral")
    doctor_name: Mapped[str] = mapped_column(String(150), default="Médico não especificado")
    specialty: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    appointment_date: Mapped[date] = mapped_column(Date, index=True)
    appointment_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reminded_day_before: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_day_of: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_hours_before: Mapped[bool] = mapped_column(Boolean, default=False)

    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_name: Mapped[str] = mapped_column(String(100), default="Geral")
    doc_type: Mapped[str] = mapped_column(String(50), default="receita")  # receita, exame, dieta, etc.
    doctor_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    doc_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    medications: Mapped[List["Medication"]] = relationship(
        "Medication", back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class DietaryProfile(Base):
    __tablename__ = "dietary_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    prohibited_items: Mapped[str] = mapped_column(Text)
    restricted_items: Mapped[str] = mapped_column(Text)
    allowed_items: Mapped[str] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FoodCheck(Base):
    __tablename__ = "food_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_name: Mapped[str] = mapped_column(String(100), default="Newton", index=True)
    product_name: Mapped[str] = mapped_column(String(200), default="Alimento não especificado")
    status: Mapped[str] = mapped_column(String(50))  # LIBERADO, ATENCAO, PROIBIDO, NAO_IDENTIFICADO
    summary: Mapped[str] = mapped_column(Text)
    identified_ingredients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    patient_name: Mapped[str] = mapped_column(String(100), default="Geral")
    doctor_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    prescription_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    name: Mapped[str] = mapped_column(String(150))
    dosage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    frequency: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["Document"] = relationship("Document", back_populates="medications")


# Inicialização assíncrona do Engine
engine_kwargs = {"echo": False}
if "postgresql+asyncpg" in DATABASE_URL:
    # Compatibilidade com pooling do Supabase (Supavisor / PgBouncer)
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_default_dietary_profiles()


# Métodos de consulta e salvamento
async def get_or_create_user(telegram_id: int, name: str) -> User:
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, name=name, patient_alias=name)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def add_appointment(
    patient_name: str,
    doctor_name: str,
    specialty: Optional[str],
    appointment_date: date,
    appointment_time: Optional[time],
    location: Optional[str],
    notes: Optional[str],
    telegram_chat_id: int,
) -> Appointment:
    async with AsyncSessionLocal() as session:
        apt = Appointment(
            patient_name=patient_name,
            doctor_name=doctor_name,
            specialty=specialty,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            location=location,
            notes=notes,
            telegram_chat_id=telegram_chat_id,
        )
        session.add(apt)
        await session.commit()
        await session.refresh(apt)
        return apt


async def get_upcoming_appointments(from_date: date) -> List[Appointment]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Appointment)
            .where(Appointment.appointment_date >= from_date)
            .order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def add_document_with_medications(
    patient_name: str,
    doc_type: str,
    doctor_name: Optional[str],
    doc_date: Optional[date],
    raw_text: Optional[str],
    summary: str,
    file_id: Optional[str],
    file_path: Optional[str],
    telegram_chat_id: int,
    medications_data: List[dict],
) -> Document:
    async with AsyncSessionLocal() as session:
        doc = Document(
            patient_name=patient_name,
            doc_type=doc_type,
            doctor_name=doctor_name,
            doc_date=doc_date,
            raw_text=raw_text,
            summary=summary,
            file_id=file_id,
            file_path=file_path,
            telegram_chat_id=telegram_chat_id,
        )
        session.add(doc)
        await session.flush()

        for med in medications_data:
            medication = Medication(
                document_id=doc.id,
                patient_name=patient_name,
                doctor_name=doctor_name,
                prescription_date=doc_date,
                name=med.get("name", ""),
                dosage=med.get("dosage"),
                frequency=med.get("frequency"),
                instructions=med.get("instructions"),
            )
            session.add(medication)

        await session.commit()
        await session.refresh(doc)
        return doc


async def get_recent_documents(limit: int = 15) -> List[Document]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Document)
            .order_by(desc(Document.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_all_medications(limit: int = 50) -> List[Medication]:
    async with AsyncSessionLocal() as session:
        stmt = select(Medication).order_by(desc(Medication.created_at)).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ==========================================
# RESTRIÇÕES ALIMENTARES E PERFIS DIETÉTICOS
# ==========================================

NEWTON_DEFAULT_PROHIBITED = (
    "GLÚTEN 100% PROIBIDO (trigo, cevada, centeio, aveia convencional sem selo, malte, extrato de malte, "
    "farinha de trigo, pães convencionais, massas convencionais, bolos e salgados convencionais, farinha de rosca). "
    "LACTOSE / DERIVADOS DE LEITE CONVENCIONAIS (leite comum com lactose, creme de leite comum, queijos com lactose, "
    "soro de leite/whey concentrado com lactose). "
    "Temperos ultraprocessados contendo alho e cebola concentrados ou realçadores artificiais de sabor."
)

NEWTON_DEFAULT_RESTRICTED = (
    "Atenção rigorosa às quantidades máximas permitidas:\n"
    "• Feijão: máximo 80g (1 concha pequena)\n"
    "• Cebola roxa refogada: máximo 30g (2 colheres de sopa)\n"
    "• Alho: máximo 1 dente por panela\n"
    "• Beterraba cozida: máximo 60g (3 colheres de sopa)\n"
    "• Molho de tomate caseiro: máximo 60g (3 colheres de sopa)\n"
    "• Café: máximo 2 xícaras por dia\n"
    "• Brócolis: apenas floretes (evitar talos)"
)

NEWTON_DEFAULT_ALLOWED = (
    "• Proteínas: Frango (150g filé), carne magra/moída (150g), peixe fresco (150g), ovos (3 un / 150g), "
    "Carnibol Darkness baunilha (30g / 1 scoop).\n"
    "• Carboidratos sem glúten: Arroz (120g / 6 colheres), cuscuz de milho (100g / 5 colheres), "
    "tapioca (40g / 3 colheres), batata, batata-doce (150g / 1 média), pão sem glúten (50g / 2 fatias), "
    "macarrão sem glúten (120g / 1 prato raso - arroz ou milho), farinha de flocão de milho.\n"
    "• Aveia: Aveia exclusivamente com selo sem glúten.\n"
    "• Legumes: Cenoura, abobrinha, chuchu, abóbora, vagem, brócolis (floretes).\n"
    "• Frutas: Kiwi (75g / 1 un), banana (80g / 1 pequena), mamão (140g / 1 fatia), melão (120g / 1 fatia), morango (100g / 7 un).\n"
    "• Gorduras e Fibras: Azeite de oliva, castanha-do-pará, chia, linhaça, psyllium.\n"
    "• Leites: Leite de aveia sem glúten (200ml / 1 copo) ou leite zero lactose (200ml / 1 copo). No molho: leite de aveia.\n"
    "• Temperos permitidos: Cebolinha, salsinha, orégano, cúrcuma, gengibre, chá de camomila."
)

NEWTON_DEFAULT_NOTES = (
    "Metas de saúde: Intestino funcionando todo dia. Consumir kiwi antes do café, do almoço e do jantar. "
    "Psyllium 2 vezes ao dia com 1 copo de água. Água: 2,5 a 2,7 litros por dia. Treino e banho gelado depois."
)

JANAINA_DEFAULT_PROHIBITED = (
    "Nenhuma restrição severa cadastrada inicialmente. Evitar alimentos excessivamente ultraprocessados."
)

JANAINA_DEFAULT_RESTRICTED = (
    "Alimentos com excesso de açúcares refinados ou gorduras trans."
)

JANAINA_DEFAULT_ALLOWED = (
    "Alimentação saudável e equilibrada: proteínas magras, frutas frescas, legumes, verduras e grãos."
)

JANAINA_DEFAULT_NOTES = (
    "Perfil da Janaína ativo no Liam. Newton ou Janaína podem cadastrar restrições específicas (como glúten, lactose, frutos do mar) a qualquer momento."
)


async def seed_default_dietary_profiles():
    """Garante que existam perfis de restrição alimentar iniciais para Newton e Janaína."""
    async with AsyncSessionLocal() as session:
        # Perfil Newton
        stmt = select(DietaryProfile).where(DietaryProfile.patient_name == "Newton")
        res = await session.execute(stmt)
        profile_newton = res.scalar_one_or_none()
        if not profile_newton:
            profile_newton = DietaryProfile(
                patient_name="Newton",
                prohibited_items=NEWTON_DEFAULT_PROHIBITED,
                restricted_items=NEWTON_DEFAULT_RESTRICTED,
                allowed_items=NEWTON_DEFAULT_ALLOWED,
                notes=NEWTON_DEFAULT_NOTES,
            )
            session.add(profile_newton)

        # Perfil Janaína
        stmt = select(DietaryProfile).where(DietaryProfile.patient_name == "Janaína")
        res = await session.execute(stmt)
        profile_janaina = res.scalar_one_or_none()
        if not profile_janaina:
            # Verifica se existe como Jana
            stmt_alt = select(DietaryProfile).where(DietaryProfile.patient_name == "Jana")
            res_alt = await session.execute(stmt_alt)
            profile_janaina = res_alt.scalar_one_or_none()

        if not profile_janaina:
            profile_janaina = DietaryProfile(
                patient_name="Janaína",
                prohibited_items=JANAINA_DEFAULT_PROHIBITED,
                restricted_items=JANAINA_DEFAULT_RESTRICTED,
                allowed_items=JANAINA_DEFAULT_ALLOWED,
                notes=JANAINA_DEFAULT_NOTES,
            )
            session.add(profile_janaina)

        await session.commit()


async def get_dietary_profile(patient_name: str) -> Optional[DietaryProfile]:
    """Retorna o perfil alimentar de um paciente específico (busca flexível: Newton, Janaína, Jana)."""
    norm = patient_name.strip().lower()
    async with AsyncSessionLocal() as session:
        stmt = select(DietaryProfile)
        res = await session.execute(stmt)
        profiles = res.scalars().all()

        for p in profiles:
            p_norm = p.patient_name.strip().lower()
            if norm == p_norm or norm in p_norm or p_norm in norm:
                return p
            if "jana" in norm and "jana" in p_norm:
                return p
            if "newt" in norm and "newt" in p_norm:
                return p
        return None


async def get_all_dietary_profiles() -> List[DietaryProfile]:
    """Retorna todos os perfis alimentares cadastrados."""
    async with AsyncSessionLocal() as session:
        stmt = select(DietaryProfile).order_by(DietaryProfile.patient_name.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def save_or_update_dietary_profile(
    patient_name: str,
    prohibited_items: Optional[str] = None,
    restricted_items: Optional[str] = None,
    allowed_items: Optional[str] = None,
    notes: Optional[str] = None,
) -> DietaryProfile:
    """Atualiza ou cria o perfil alimentar de uma pessoa."""
    target_name = "Janaína" if "jana" in patient_name.lower() else ("Newton" if "newt" in patient_name.lower() else patient_name.title())

    async with AsyncSessionLocal() as session:
        stmt = select(DietaryProfile).where(DietaryProfile.patient_name == target_name)
        res = await session.execute(stmt)
        profile = res.scalar_one_or_none()

        if not profile:
            profile = DietaryProfile(
                patient_name=target_name,
                prohibited_items=prohibited_items or "Nenhuma restrição proibida cadastrada.",
                restricted_items=restricted_items or "Nenhuma restrição moderada cadastrada.",
                allowed_items=allowed_items or "Alimentos gerais saudáveis.",
                notes=notes or "",
            )
            session.add(profile)
        else:
            if prohibited_items is not None:
                profile.prohibited_items = prohibited_items
            if restricted_items is not None:
                profile.restricted_items = restricted_items
            if allowed_items is not None:
                profile.allowed_items = allowed_items
            if notes is not None:
                profile.notes = notes
            profile.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(profile)
        return profile


async def add_food_check(
    patient_name: str,
    product_name: str,
    status: str,
    summary: str,
    identified_ingredients: Optional[str],
    telegram_chat_id: int,
) -> FoodCheck:
    """Registra uma verificação de alimento ou rótulo no histórico."""
    async with AsyncSessionLocal() as session:
        check = FoodCheck(
            patient_name=patient_name,
            product_name=product_name,
            status=status,
            summary=summary,
            identified_ingredients=identified_ingredients,
            telegram_chat_id=telegram_chat_id,
        )
        session.add(check)
        await session.commit()
        await session.refresh(check)
        return check


async def get_recent_food_checks(patient_name: Optional[str] = None, limit: int = 10) -> List[FoodCheck]:
    """Lista as verificações de alimentos recentes."""
    async with AsyncSessionLocal() as session:
        stmt = select(FoodCheck).order_by(desc(FoodCheck.created_at))
        if patient_name:
            target = "Janaína" if "jana" in patient_name.lower() else ("Newton" if "newt" in patient_name.lower() else patient_name)
            stmt = stmt.where(FoodCheck.patient_name == target)
        stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

