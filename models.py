from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey,
    Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 1. Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    profile: Mapped[Optional["Profile"]] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    daily_logs: Mapped[List["DailyLog"]] = relationship(
        "DailyLog", back_populates="user", cascade="all, delete-orphan"
    )
    meals: Mapped[List["Meal"]] = relationship(
        "Meal", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# 2. Profiles
# ---------------------------------------------------------------------------

class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    gender: Mapped[str] = mapped_column(String(10), nullable=False)          # "male" | "female"
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    current_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    target_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    goal: Mapped[str] = mapped_column(String(20), nullable=False)            # "lose_weight" | "maintain" | "gain_muscle"
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False)  # "sedentary" | "light" | "moderate" | "active" | "very_active"
    daily_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_water_goal_ml: Mapped[int] = mapped_column(Integer, default=2500, nullable=False)
    daily_steps_goal: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return (
            f"<Profile user_id={self.user_id} goal={self.goal!r} "
            f"daily_calories={self.daily_calories}>"
        )


# ---------------------------------------------------------------------------
# 3. Daily Logs
# ---------------------------------------------------------------------------

class DailyLog(Base):
    __tablename__ = "daily_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_daily_logs_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    calories_eaten: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    water_ml: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="daily_logs")
    meals: Mapped[List["Meal"]] = relationship(
        "Meal", back_populates="daily_log", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DailyLog id={self.id} user_id={self.user_id} date={self.date}>"


# ---------------------------------------------------------------------------
# 4. Meals
# ---------------------------------------------------------------------------

class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    daily_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("daily_logs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "breakfast" | "lunch" | "dinner" | "snack"
    source: Mapped[str] = mapped_column(String(20), nullable=False)     # "manual" | "scan"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="meals")
    daily_log: Mapped["DailyLog"] = relationship("DailyLog", back_populates="meals")

    def __repr__(self) -> str:
        return (
            f"<Meal id={self.id} name={self.name!r} "
            f"calories={self.calories} type={self.meal_type!r}>"
        )


# ---------------------------------------------------------------------------
# 5. Foods  (global food database)
# ---------------------------------------------------------------------------

class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_uz: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    calories_per_100g: Mapped[float] = mapped_column(Float, nullable=False)
    protein_per_100g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    carbs_per_100g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fat_per_100g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # "grain" | "meat" | "vegetable" | "fruit" | "dairy" | "drink" | "snack" | "dish"

    def __repr__(self) -> str:
        return (
            f"<Food id={self.id} name_uz={self.name_uz!r} "
            f"cal/100g={self.calories_per_100g}>"
        )
