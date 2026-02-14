import aiosqlite


async def upsert_user(
    db: aiosqlite.Connection,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    await db.execute(
        """
        INSERT INTO users (id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, username, first_name, last_name),
    )
    await db.commit()
