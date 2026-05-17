import base64
import json
import re
from datetime import date
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import DailyLog, Meal, User
from app.schemas import MealResponse, ScanResult

router = APIRouter(prefix="/scan", tags=["scan"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={api_key}"
)

GEMINI_PROMPT = (
    'Analyze this food image. Return ONLY valid JSON with no markdown. '
    'Format: {"food_name": "...", "calories": 0, "protein_g": 0.0, '
    '"carbs_g": 0.0, "fat_g": 0.0, "confidence": 0.0, "alternatives": ["..."]}. '
    "Estimate calories for a typical single serving."
)

# Accepted MIME types — Gemini supports these image formats
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fences(text: str) -> str:
    """Remove ```json … ``` or ``` … ``` wrappers Gemini sometimes adds."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def _call_gemini(image_bytes: bytes, mime_type: str) -> dict:
    """
    Send the image to Gemini 1.5 Flash and return the parsed JSON dict.
    Raises HTTPException(502) on network errors and HTTPException(400)
    if the model response cannot be parsed.
    """
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_image,
                        }
                    },
                    {"text": GEMINI_PROMPT},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,      # low temp → more deterministic nutrition values
            "maxOutputTokens": 256,  # the JSON response is small; cap tokens
        },
    }

    url = GEMINI_URL.format(api_key=settings.GEMINI_API_KEY)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Gemini API timed out — try again",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Gemini API: {exc}",
        )

    try:
        gemini_data = response.json()
        raw_text: str = gemini_data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not analyze image — unexpected Gemini response structure",
        )

    clean_text = _strip_markdown_fences(raw_text)

    try:
        result: dict = json.loads(clean_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not analyze image — model returned non-JSON output",
        )

    return result


def _parse_scan_result(data: dict) -> ScanResult:
    """Safely map Gemini's dict to our ScanResult schema with fallback defaults."""
    try:
        return ScanResult(
            food_name=str(data.get("food_name", "Unknown food")),
            calories=int(data.get("calories", 0)),
            protein_g=float(data.get("protein_g", 0.0)),
            carbs_g=float(data.get("carbs_g", 0.0)),
            fat_g=float(data.get("fat_g", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            alternatives=[str(a) for a in data.get("alternatives", [])],
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not analyze image — malformed model output: {exc}",
        )


def _get_or_create_today_log(user_id: int, db: Session) -> DailyLog:
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


# ---------------------------------------------------------------------------
# 1. POST /scan  — analyze image with Gemini
# ---------------------------------------------------------------------------

@router.post("", response_model=ScanResult)
async def scan_food(
    file: UploadFile = File(..., description="Food photo (JPEG / PNG / WebP)"),
) -> Any:
    """
    Accept a food image and return AI-estimated nutrition via Gemini 1.5 Flash.
    Auth is intentionally optional here: the Mini App calls this before the user
    confirms adding the meal, then sends the result to POST /scan/confirm.
    """
    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. "
                   f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    image_bytes = await file.read()

    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large (max {MAX_IMAGE_BYTES // 1024 // 1024} MB)",
        )

    raw = await _call_gemini(image_bytes, content_type)
    return _parse_scan_result(raw)


# ---------------------------------------------------------------------------
# 2. POST /scan/confirm  — save the scanned meal to today's log
# ---------------------------------------------------------------------------

class ConfirmScanRequest(BaseModel):
    scan_result: ScanResult
    meal_type: str = "snack"   # "breakfast" | "lunch" | "dinner" | "snack"


@router.post("/confirm", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
async def confirm_scan(
    body: ConfirmScanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    """
    Persist a previously scanned meal to the user's daily log.
    Mirrors POST /meals but pre-filled from the AI scan result.
    """
    log = _get_or_create_today_log(user.telegram_id, db)

    # First meal of the day → mark streak
    if log.calories_eaten == 0:
        log.streak_day = True

    meal = Meal(
        user_id=user.telegram_id,
        daily_log_id=log.id,
        name=body.scan_result.food_name,
        calories=body.scan_result.calories,
        protein_g=body.scan_result.protein_g,
        carbs_g=body.scan_result.carbs_g,
        fat_g=body.scan_result.fat_g,
        meal_type=body.meal_type,
        source="scan",
    )
    db.add(meal)
    log.calories_eaten += body.scan_result.calories
    db.commit()
    db.refresh(meal)
    return MealResponse.model_validate(meal)

