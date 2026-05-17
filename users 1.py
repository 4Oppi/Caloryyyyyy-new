import json
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_access_token, verify_telegram_init_data
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import DailyLog, Profile, User
from app.schemas import OnboardingData, ProfileResponse, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Activity multipliers (Mifflin-St Jeor / TDEE)
# ---------------------------------------------------------------------------

ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary":   1.2,
    "light":       1.375,
    "moderate":    1.55,
    "active":      1.725,
    "very_active": 1.9,
}


def calculate_daily_calories(
    gender: str,
    age: int,
    height_cm: int,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> int:
    """
    Mifflin-St Jeor BMR → TDEE → goal adjustment.

    BMR (male)   = 10*weight + 6.25*height - 5*age + 5
    BMR (female) = 10*weight + 6.25*height - 5*age - 161
    TDEE         = BMR * activity_multiplier
    Goal adj.    = lose_weight: -500 | gain_muscle: +300 | maintain: 0
    """
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        bmr += 5
    else:
        bmr -= 161

    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
    tdee = bmr * multiplier

    if goal == "lose_weight":
        tdee -= 500
    elif goal == "gain_muscle":
        tdee += 300

    return max(1200, round(tdee))  # never go below a safe floor


# ---------------------------------------------------------------------------
# Request / response body schemas (inline — avoids polluting schemas.py)
# ---------------------------------------------------------------------------

class TelegramAuthRequest(BaseModel):
    init_data: str


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    onboarding_done: bool


class ProfileUpdateRequest(BaseModel):
    """All fields optional — only provided fields are updated."""
    gender: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[int] = None
    current_weight_kg: Optional[float] = None
    target_weight_kg: Optional[float] = None
    goal: Optional[str] = None
    activity_level: Optional[str] = None
    daily_water_goal_ml: Optional[int] = None
    daily_steps_goal: Optional[int] = None


# ---------------------------------------------------------------------------
# 1. POST /auth/telegram
# ---------------------------------------------------------------------------

@router.post("/auth/telegram", response_model=TelegramAuthResponse)
async def telegram_auth(
    body: TelegramAuthRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Verify Telegram WebApp initData, upsert User, and return a JWT.
    This endpoint is intentionally public (no Depends(get_current_user)).
    """
    # Verify HMAC signature and parse initData
    params = verify_telegram_init_data(body.init_data, settings.BOT_TOKEN)

    # Extract user object embedded as JSON string
    user_json_str = params.get("user")
    if not user_json_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="initData missing 'user' field",
        )

    try:
        tg_user: dict = json.loads(user_json_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="initData 'user' field is not valid JSON",
        )

    telegram_id: int = int(tg_user["id"])
    first_name: str = tg_user.get("first_name", "")
    last_name: str = tg_user.get("last_name", "")
    name: str = f"{first_name} {last_name}".strip() or None

    # Upsert user
    user = db.get(User, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif name and user.name != name:
        # Keep name in sync if Telegram profile changed
        user.name = name
        db.commit()
        db.refresh(user)

    onboarding_done: bool = (
        user.profile is not None and user.profile.onboarding_done
    )

    access_token = create_access_token(
        {"sub": str(telegram_id)}, secret=settings.JWT_SECRET
    )

    return TelegramAuthResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        onboarding_done=onboarding_done,
    )


# ---------------------------------------------------------------------------
# 2. POST /onboarding
# ---------------------------------------------------------------------------

@router.post("/onboarding", response_model=ProfileResponse)
async def onboarding(
    body: OnboardingData,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """
    Save first-time profile data, calculate TDEE, and create today's DailyLog.
    Idempotent: re-running overwrites the existing profile.
    """
    daily_calories = calculate_daily_calories(
        gender=body.gender,
        age=body.age,
        height_cm=body.height_cm,
        weight_kg=body.current_weight_kg,
        activity_level=body.activity_level,
        goal=body.goal,
    )

    profile = db.get(Profile, user.telegram_id)
    if profile is None:
        profile = Profile(user_id=user.telegram_id)
        db.add(profile)

    profile.gender = body.gender
    profile.age = body.age
    profile.height_cm = body.height_cm
    profile.current_weight_kg = body.current_weight_kg
    profile.target_weight_kg = body.target_weight_kg
    profile.goal = body.goal
    profile.activity_level = body.activity_level
    profile.daily_calories = daily_calories
    profile.onboarding_done = True

    # Ensure today's DailyLog exists
    today = date.today()
    existing_log = (
        db.query(DailyLog)
        .filter(DailyLog.user_id == user.telegram_id, DailyLog.date == today)
        .first()
    )
    if existing_log is None:
        db.add(DailyLog(user_id=user.telegram_id, date=today))

    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# 3. GET /me
# ---------------------------------------------------------------------------

class MeResponse(BaseModel):
    user: UserResponse
    profile: Optional[ProfileResponse] = None


@router.get("/me", response_model=MeResponse)
async def get_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """Return the authenticated user and their profile."""
    return MeResponse(
        user=UserResponse.model_validate(user),
        profile=(
            ProfileResponse.model_validate(user.profile)
            if user.profile is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# 4. PUT /profile
# ---------------------------------------------------------------------------

@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """
    Partial profile update.  Any field left as None is left unchanged.
    Recalculates daily_calories if any calorie-affecting field changes.
    """
    profile = db.get(Profile, user.telegram_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found — complete onboarding first",
        )

    # Apply only the fields that were explicitly provided
    calorie_fields = {"gender", "age", "height_cm", "current_weight_kg", "activity_level", "goal"}
    recalculate = False

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
        if field in calorie_fields:
            recalculate = True

    if recalculate:
        profile.daily_calories = calculate_daily_calories(
            gender=profile.gender,
            age=profile.age,
            height_cm=profile.height_cm,
            weight_kg=profile.current_weight_kg,
            activity_level=profile.activity_level,
            goal=profile.goal,
        )

    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)

