import aiosqlite


async def is_whitelisted(db: aiosqlite.Connection, user_id: int) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
    )
    return await cursor.fetchone() is not None


async def add_to_whitelist(
    db: aiosqlite.Connection,
    user_id: int,
    added_by: int,
    note: str | None = None,
) -> bool:
    """Add user to whitelist. Returns True if added, False if already existed."""
    try:
        await db.execute(
            "INSERT INTO whitelist (user_id, added_by, note) VALUES (?, ?, ?)",
            (user_id, added_by, note),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_from_whitelist(db: aiosqlite.Connection, user_id: int) -> bool:
    """Remove user from whitelist. Returns True if removed, False if not found."""
    cursor = await db.execute(
        "DELETE FROM whitelist WHERE user_id = ?", (user_id,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_whitelist(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT w.user_id, w.note, w.created_at, u.username, u.first_name
        FROM whitelist w
        LEFT JOIN users u ON u.id = w.user_id
        ORDER BY w.created_at DESC
        """
    )
    rows = await cursor.fetchall()
    return [
        {
            "user_id": row[0],
            "note": row[1],
            "created_at": row[2],
            "username": row[3],
            "first_name": row[4],
        }
        for row in rows
    ]
