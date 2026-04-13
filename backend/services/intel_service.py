import logging
from datetime import datetime, date
from bson import ObjectId
from database.mongodb import get_db
from models.intel import IntelTransactionDB, IntelTransactionType
from models.prediction import PredictionDB

logger = logging.getLogger(__name__)


def calculate_win_payout(intel_wagered: int, confidence: int) -> int:
    """
    Higher payout for lower-confidence correct predictions (you took more risk).
    confidence=40 → 2.5x | confidence=95 → 1.05x
    """
    multiplier = 1 + ((100 - confidence) / 60)
    return int(intel_wagered * multiplier)


def calculate_daily_login_intel(streak: int) -> tuple[int, bool]:
    """Returns (intel_amount, streak_complete)."""
    streak_complete = streak > 0 and streak % 7 == 0
    if streak_complete:
        return 100, True
    return 25, False


async def award_intel(
    agent_id: str,
    user_id: str,
    amount: int,
    tx_type: IntelTransactionType,
    description: str,
    reference_id: str | None = None,
) -> int:
    """
    Awards INTEL to an agent. Returns new balance.
    Updates agent.intel_balance and creates a transaction record atomically.
    """
    db = get_db()

    # Get current balance
    agent = await db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    current_balance = agent.get("intel_balance", 0)
    new_balance = max(0, current_balance + amount)

    # Update agent balance
    await db.agents.update_one(
        {"_id": ObjectId(agent_id)},
        {"$set": {"intel_balance": new_balance, "updated_at": datetime.utcnow()}},
    )

    # Create transaction record
    tx = IntelTransactionDB(
        agent_id=agent_id,
        user_id=user_id,
        amount=amount,
        type=tx_type,
        reference_id=reference_id,
        description=description,
        running_balance=new_balance,
    )
    tx_doc = tx.model_dump(exclude={"id"})
    await db.intel_transactions.insert_one(tx_doc)

    logger.info(f"Intel awarded: agent={agent_id} amount={amount} type={tx_type} new_balance={new_balance}")
    return new_balance


async def claim_daily_login(user_id: str, agent_id: str) -> dict:
    """
    Processes daily login reward. Enforces one claim per calendar day.
    Returns {"intel_awarded": int, "new_balance": int, "streak": int, "streak_complete": bool}
    """
    db = get_db()
    today_str = date.today().isoformat()

    # Check user's last login date
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise ValueError("User not found")

    last_login_date = user.get("last_login_date", "")
    if last_login_date == today_str:
        raise ValueError("Daily reward already claimed today")

    # Calculate streak
    yesterday_str = (date.today().fromordinal(date.today().toordinal() - 1)).isoformat()
    current_streak = user.get("login_streak", 0)

    if last_login_date == yesterday_str:
        new_streak = current_streak + 1
    else:
        new_streak = 1  # streak broken, reset to 1

    intel_amount, streak_complete = calculate_daily_login_intel(new_streak)

    # Update user streak
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "login_streak": new_streak,
                "last_login_date": today_str,
                "last_login": datetime.utcnow(),
            }
        },
    )

    tx_type = IntelTransactionType.streak_bonus if streak_complete else IntelTransactionType.daily_login
    description = (
        f"7-day streak bonus! 🔥" if streak_complete
        else f"Daily login reward (day {new_streak})"
    )

    new_balance = await award_intel(
        agent_id=agent_id,
        user_id=user_id,
        amount=intel_amount,
        tx_type=tx_type,
        description=description,
    )

    return {
        "intel_awarded": intel_amount,
        "new_balance": new_balance,
        "streak": new_streak,
        "streak_complete": streak_complete,
        "message": description,
    }


async def deduct_wager(agent_id: str, amount: int) -> int:
    """Deducts a wager from agent balance. Returns new balance."""
    db = get_db()
    agent = await db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        raise ValueError("Agent not found")
    current = agent.get("intel_balance", 0)
    if current < amount:
        raise ValueError(f"Insufficient balance: {current} < {amount}")
    new_balance = current - amount
    await db.agents.update_one(
        {"_id": ObjectId(agent_id)},
        {"$set": {"intel_balance": new_balance, "updated_at": datetime.utcnow()}},
    )
    return new_balance
