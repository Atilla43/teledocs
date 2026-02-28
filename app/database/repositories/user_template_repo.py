import json

import aiosqlite


async def save_user_template(
    db: aiosqlite.Connection,
    user_id: int,
    template_name: str,
    filename: str,
    fields: list[dict],
) -> int:
    cursor = await db.execute(
        """
        INSERT INTO user_templates (user_id, template_name, filename, fields_json)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, template_name, filename, json.dumps(fields, ensure_ascii=False)),
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_templates(
    db: aiosqlite.Connection, user_id: int
) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT id, template_name, filename, fields_json, created_at
        FROM user_templates
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "template_name": row[1],
            "filename": row[2],
            "fields": json.loads(row[3]),
            "created_at": row[4],
        }
        for row in rows
    ]


async def get_user_template_by_id(
    db: aiosqlite.Connection, template_id: int, user_id: int
) -> dict | None:
    cursor = await db.execute(
        """
        SELECT id, template_name, filename, fields_json
        FROM user_templates
        WHERE id = ? AND user_id = ?
        """,
        (template_id, user_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "template_name": row[1],
        "filename": row[2],
        "fields": json.loads(row[3]),
    }


async def delete_user_template(
    db: aiosqlite.Connection, template_id: int, user_id: int
) -> bool:
    cursor = await db.execute(
        "DELETE FROM user_templates WHERE id = ? AND user_id = ?",
        (template_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0
