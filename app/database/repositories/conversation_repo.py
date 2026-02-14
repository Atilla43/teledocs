import aiosqlite


async def save_message(
    db: aiosqlite.Connection,
    user_id: int,
    role: str,
    content: str,
) -> None:
    await db.execute(
        "INSERT INTO conversation_history (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    await db.commit()


async def get_history(
    db: aiosqlite.Connection,
    user_id: int,
    limit: int = 20,
) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT role, content FROM conversation_history
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
