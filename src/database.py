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
