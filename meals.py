from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import DailyLog, Food, Meal, User
from app.schemas import DailyStats, FoodResponse, MealResponse

router = APIRouter(tags=["meals"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_or_create_today_log(user_id: int, db: Session) -> DailyLog:
    """Return today's DailyLog, creating it if it doesn't exist yet."""
    today = date.today()
    log = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == user_id, DailyLog.date == today)
        .first()
    )
    if log is None:
        log = DailyLog(user_id=user_id, date=today)
        db.add(log)
        db.commit()
        db.refresh(log)
    return log


def count_current_streak(user_id: int, db: Session) -> int:
    """
    Count consecutive days with streak_day=True ending on today (or yesterday
    if today hasn't been logged yet).  Walks backwards day-by-day.
    """
    streak = 0
    check_date = date.today()
    while True:
        log = (
            db.query(DailyLog)
            .filter(DailyLog.user_id == user_id, DailyLog.date == check_date)
            .first()
        )
        if log is None or not log.streak_day:
            break
        streak += 1
        check_date -= timedelta(days=1)
    return streak


def count_longest_streak(user_id: int, db: Session) -> int:
    """
    Scan all daily_logs in ascending date order and find the longest
    consecutive run of streak_day=True.
    """
    logs = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == user_id, DailyLog.streak_day.is_(True))
        .order_by(DailyLog.date)
        .all()
    )
    if not logs:
        return 0

    longest = current = 1
    for i in range(1, len(logs)):
        if (logs[i].date - logs[i - 1].date).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class AddMealRequest(BaseModel):
    name: str
    calories: int
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    meal_type: str          # "breakfast" | "lunch" | "dinner" | "snack"
    source: str = "manual"  # "manual" | "scan"
    food_id: Optional[int] = None  # reference to Food table (optional)


class WaterRequest(BaseModel):
    amount_ml: int = 250


class WaterResponse(BaseModel):
    water_ml: int
    water_goal: int
    percentage: float


class StepsRequest(BaseModel):
    steps: int


class StepsResponse(BaseModel):
    steps: int
    steps_goal: int
    percentage: float


class StreakResponse(BaseModel):
    current_streak: int
    longest_streak: int


# ---------------------------------------------------------------------------
# 1. POST /meals
# ---------------------------------------------------------------------------

@router.post("/meals", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
async def add_meal(
    body: AddMealRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Add a meal to today's log and update calorie totals."""
    log = get_or_create_today_log(user.telegram_id, db)

    # First meal of the day → mark as streak day
    is_first_meal = log.calories_eaten == 0
    if is_first_meal:
        log.streak_day = True

    meal = Meal(
        user_id=user.telegram_id,
        daily_log_id=log.id,
        name=body.name,
        calories=body.calories,
        protein_g=body.protein_g,
        carbs_g=body.carbs_g,
        fat_g=body.fat_g,
        meal_type=body.meal_type,
        source=body.source,
    )
    db.add(meal)

    log.calories_eaten += body.calories
    db.commit()
    db.refresh(meal)
    return MealResponse.model_validate(meal)


# ---------------------------------------------------------------------------
# 2. GET /daily/today
# ---------------------------------------------------------------------------

@router.get("/daily/today", response_model=DailyStats)
async def get_today(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Return today's aggregated stats for the home screen."""
    log = get_or_create_today_log(user.telegram_id, db)

    profile = user.profile
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not set up — complete onboarding first",
        )

    meals_count = (
        db.query(Meal)
        .filter(Meal.daily_log_id == log.id)
        .count()
    )

    return DailyStats(
        calories_eaten=log.calories_eaten,
        calories_goal=profile.daily_calories,
        water_ml=log.water_ml,
        water_goal=profile.daily_water_goal_ml,
        steps=log.steps,
        steps_goal=profile.daily_steps_goal,
        meals_count=meals_count,
        streak_days=count_current_streak(user.telegram_id, db),
    )


# ---------------------------------------------------------------------------
# 3. POST /water
# ---------------------------------------------------------------------------

@router.post("/water", response_model=WaterResponse)
async def add_water(
    body: WaterRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Add water intake (default +250 ml) to today's log."""
    if body.amount_ml <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount_ml must be a positive integer",
        )

    log = get_or_create_today_log(user.telegram_id, db)
    log.water_ml += body.amount_ml
    db.commit()
    db.refresh(log)

    water_goal = user.profile.daily_water_goal_ml if user.profile else 2500
    percentage = round(min(log.water_ml / water_goal * 100, 100), 1)

    return WaterResponse(
        water_ml=log.water_ml,
        water_goal=water_goal,
        percentage=percentage,
    )


# ---------------------------------------------------------------------------
# 4. POST /steps
# ---------------------------------------------------------------------------

@router.post("/steps", response_model=StepsResponse)
async def update_steps(
    body: StepsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """
    Set today's step count (replace, not add — user sends cumulative total
    from their phone's pedometer).
    """
    if body.steps < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="steps cannot be negative",
        )

    log = get_or_create_today_log(user.telegram_id, db)
    log.steps = body.steps
    db.commit()
    db.refresh(log)

    steps_goal = user.profile.daily_steps_goal if user.profile else 10000
    percentage = round(min(log.steps / steps_goal * 100, 100), 1)

    return StepsResponse(
        steps=log.steps,
        steps_goal=steps_goal,
        percentage=percentage,
    )


# ---------------------------------------------------------------------------
# 5. GET /foods
# ---------------------------------------------------------------------------

@router.get("/foods", response_model=List[FoodResponse])
async def search_foods(
    q: str = Query(default="", min_length=0, description="Search term (Uzbek food name)"),
    db: Session = Depends(get_db),
) -> Any:
    """
    Case-insensitive search of the global food database by Uzbek name.
    No auth required — open endpoint.
    Returns up to 20 results.
    """
    query = db.query(Food)
    if q.strip():
        query = query.filter(Food.name_uz.ilike(f"%{q.strip()}%"))
    foods = query.limit(20).all()
    return [FoodResponse.model_validate(f) for f in foods]


# ---------------------------------------------------------------------------
# 6. GET /streak
# ---------------------------------------------------------------------------

@router.get("/streak", response_model=StreakResponse)
async def get_streak(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Return current and all-time longest streak for the authenticated user."""
    return StreakResponse(
        current_streak=count_current_streak(user.telegram_id, db),
        longest_streak=count_longest_streak(user.telegram_id, db),
    )

