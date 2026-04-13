import logging
import random
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from database.mongodb import get_db
from database.redis_client import set_json, get_json, delete_key
from models.user import RegisterRequest, LoginRequest, UserResponse, TokenResponse, MeResponse
from utils.jwt_handler import create_access_token, create_refresh_token, decode_token, get_user_id_from_token
from utils.password_handler import hash_password, verify_password
from services.email_service import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()
logger = logging.getLogger(__name__)

OTP_TTL = 600        # 10 minutes
OTP_MAX_ATTEMPTS = 5


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class SendOtpRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _user_response(user: dict, user_id: str) -> UserResponse:
    return UserResponse(
        id=user_id,
        email=user["email"],
        username=user["username"],
        login_streak=user.get("login_streak", 0),
        last_login=user.get("last_login"),
        created_at=user.get("created_at", datetime.utcnow()),
        is_verified=user.get("is_verified", True),
    )


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user_id


# ── Step 1: Validate + send OTP (nothing written to DB yet) ───────────────────
@router.post("/send-otp", status_code=200)
async def send_otp(body: SendOtpRequest):
    """
    Validates uniqueness, generates OTP, stores pending signup in Redis,
    emails the OTP. Nothing is written to MongoDB until OTP is verified.
    """
    db = get_db()

    # Validate username format
    if len(body.username) < 3:
        raise HTTPException(status_code=422, detail="Username must be at least 3 characters")
    if not all(c.isalnum() or c in "_-" for c in body.username):
        raise HTTPException(status_code=422, detail="Username can only contain letters, numbers, _ and -")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    # Check uniqueness before sending OTP
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    if await db.users.find_one({"username": body.username.lower()}):
        raise HTTPException(status_code=409, detail="Username already taken")

    # Rate limit: max 3 OTP sends per email per hour
    rate_key = f"otp_rate:{body.email}"
    from database.redis_client import get_counter, increment_counter
    sends = await get_counter(rate_key)
    if sends >= 3:
        raise HTTPException(status_code=429, detail="Too many OTP requests. Wait an hour before trying again.")
    await increment_counter(rate_key, ttl=3600)

    # Generate 6-digit OTP
    otp = f"{random.randint(0, 999999):06d}"

    # Store pending signup in Redis (pre-hash the password so it's not stored plain)
    pending = {
        "otp": otp,
        "attempts": 0,
        "username": body.username.lower(),
        "email": body.email,
        "password_hash": hash_password(body.password),
    }
    await set_json(f"otp_pending:{body.email}", pending, ttl=OTP_TTL)

    # Send OTP email (console log in dev if no email service configured)
    await send_otp_email(body.email, body.username, otp)

    logger.info(f"OTP sent to {body.email} for signup ({body.username})")
    return {"message": "OTP sent to your email", "email": body.email}


# ── Step 2: Verify OTP → create user → return JWT ─────────────────────────────
@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(body: VerifyOtpRequest):
    """
    Checks OTP against Redis, creates user in MongoDB on success, returns JWT.
    """
    db = get_db()
    redis_key = f"otp_pending:{body.email}"

    pending = await get_json(redis_key)
    if not pending:
        raise HTTPException(status_code=400, detail="OTP expired or not found. Request a new one.")

    # Track failed attempts
    attempts = pending.get("attempts", 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        await delete_key(redis_key)
        raise HTTPException(status_code=400, detail="Too many incorrect attempts. Request a new OTP.")

    if pending["otp"] != body.otp.strip():
        # Increment attempts
        pending["attempts"] = attempts + 1
        await set_json(redis_key, pending, ttl=OTP_TTL)
        remaining = OTP_MAX_ATTEMPTS - pending["attempts"]
        raise HTTPException(status_code=400, detail=f"Incorrect OTP. {remaining} attempt(s) remaining.")

    # OTP correct — consume it
    await delete_key(redis_key)

    # Final uniqueness check (race condition guard)
    if await db.users.find_one({"email": pending["email"]}):
        raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.utcnow()
    user_doc = {
        "email": pending["email"],
        "username": pending["username"],
        "password_hash": pending["password_hash"],
        "is_verified": True,          # verified via OTP — no email link needed
        "login_streak": 0,
        "last_login_date": "",
        "last_login": now,
        "created_at": now,
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    access_token = create_access_token(user_id, pending["email"])
    refresh_token = create_refresh_token(user_id)

    logger.info(f"User created via OTP: {pending['username']} ({pending['email']})")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_response(user_doc, user_id),
    )


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    db = get_db()
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = str(user["_id"])
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow()}})

    access_token = create_access_token(user_id, user["email"])
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_response(user, user_id),
    )


# ── Refresh token ─────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload["sub"]
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(user_id, user["email"])
    new_refresh = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user=_user_response(user, user_id),
    )


# ── Me ────────────────────────────────────────────────────────────────────────
@router.get("/me", response_model=MeResponse)
async def get_me(user_id: str = Depends(get_current_user_id)):
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agent = await db.agents.find_one({"user_id": user_id})
    agent_data = None
    if agent:
        agent["_id"] = str(agent["_id"])
        agent_data = agent

    return MeResponse(user=_user_response(user, user_id), agent=agent_data)
