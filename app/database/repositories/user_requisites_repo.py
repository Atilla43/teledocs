import json

import aiosqlite


async def get_user_requisites(db: aiosqlite.Connection, user_id: int) -> dict | None:
    """Get saved requisites for a user. Returns dict or None."""
    cursor = await db.execute(
        "SELECT requisites_json FROM user_requisites WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row:
        return json.loads(row[0])
    return None


async def save_user_requisites(
    db: aiosqlite.Connection, user_id: int, requisites: dict
) -> None:
    """Save or update user requisites."""
    await db.execute(
        """INSERT INTO user_requisites (user_id, requisites_json, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
             requisites_json = excluded.requisites_json,
             updated_at = CURRENT_TIMESTAMP""",
        (user_id, json.dumps(requisites, ensure_ascii=False)),
    )
    await db.commit()


async def delete_user_requisites(db: aiosqlite.Connection, user_id: int) -> bool:
    """Delete user requisites. Returns True if deleted."""
    cursor = await db.execute(
        "DELETE FROM user_requisites WHERE user_id = ?", (user_id,)
    )
    await db.commit()
    return cursor.rowcount > 0
