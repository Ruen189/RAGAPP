from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def ensure_knowledge_document_columns(conn: AsyncConnection) -> None:
    if conn.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_extension VARCHAR(16)",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS mime_type VARCHAR(128)",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS file_data BYTEA",
        "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS visible_to_users BOOLEAN DEFAULT TRUE",
        "UPDATE knowledge_documents SET file_name = COALESCE(file_name, title || '.txt') WHERE file_name IS NULL",
        "UPDATE knowledge_documents SET file_extension = COALESCE(file_extension, '.txt') WHERE file_extension IS NULL",
        "UPDATE knowledge_documents SET mime_type = COALESCE(mime_type, 'text/plain; charset=utf-8') WHERE mime_type IS NULL",
        "UPDATE knowledge_documents SET visible_to_users = COALESCE(visible_to_users, TRUE) WHERE visible_to_users IS NULL",
    ]
    for statement in statements:
        await conn.execute(text(statement))
