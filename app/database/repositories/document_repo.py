import json

import aiosqlite


async def save_document(
    db: aiosqlite.Connection,
    user_id: int,
    template_id: str,
    template_name: str,
    context: dict,
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO generated_documents (user_id, template_id, template_name, context_json)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, template_id, template_name, json.dumps(context, ensure_ascii=False)),
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_documents(
    db: aiosqlite.Connection,
    user_id: int,
    limit: int = 20,
) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT id, template_name, created_at FROM generated_documents
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [
        {"id": row[0], "template_name": row[1], "created_at": row[2]}
        for row in rows
    ]
