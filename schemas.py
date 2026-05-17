from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# 1. User schemas
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    name: Optional[str] = None


class UserCreate(UserBase):
    telegram_id: int


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    telegram_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# 2. Profile schemas
# ---------------------------------------------------------------------------

class ProfileBase(BaseModel):
    gender: str                          # "male" | "female"
    age: int
    height_cm: int
    current_weight_kg: float
    target_weight_kg: Optional[float] = None
    goal: str                            # "lose_weight" | "maintain" | "gain_muscle"
    activity_level: str                  # "sedentary" | "light" | "moderate" | "active" | "very_active"
    daily_calories: int
    daily_water_goal_ml: int = 2500
    daily_steps_goal: int = 10000
    onboarding_done: bool = False


class ProfileCreate(ProfileBase):
    user_id: int


class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    updated_at: datetime


# ---------------------------------------------------------------------------
# 3. DailyLog schemas
# ---------------------------------------------------------------------------

class DailyLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date: date
    calories_eaten: int
    water_ml: int
    steps: int
    streak_day: bool


# ---------------------------------------------------------------------------
# 4. Meal schemas
# ---------------------------------------------------------------------------

class MealBase(BaseModel):
    name: str
    calories: int
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    meal_type: str   # "breakfast" | "lunch" | "dinner" | "snack"
    source: str      # "manual" | "scan"


class MealCreate(MealBase):
    user_id: int
    daily_log_id: int


class MealResponse(MealBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    daily_log_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# 5. Food schemas
# ---------------------------------------------------------------------------

class FoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_uz: str
    name_en: Optional[str] = None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    category: str


# ---------------------------------------------------------------------------
# 6. Extra / composite schemas
# ---------------------------------------------------------------------------

class OnboardingData(BaseModel):
    """Payload sent by the Mini App during first-time setup."""
    gender: str                          # "male" | "female"
    age: int
    height_cm: int
    current_weight_kg: float
    target_weight_kg: Optional[float] = None
    goal: str                            # "lose_weight" | "maintain" | "gain_muscle"
    activity_level: str                  # "sedentary" | "light" | "moderate" | "active" | "very_active"


class DailyStats(BaseModel):
    """Aggregated stats returned by GET /daily/today."""
    calories_eaten: int
    calories_goal: int
    water_ml: int
    water_goal: int
    steps: int
    steps_goal: int
    meals_count: int
    streak_days: int


class ScanResult(BaseModel):
    """AI food scan result from Gemini API."""
    food_name: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: float                    # 0.0 – 1.0
    alternatives: List[str] = []        # other possible food names the model considered

