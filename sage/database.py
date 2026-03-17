import asyncpg
from typing import Optional
from sage.config import settings
from supabase import create_client, Client

class Database:
    def __init__(self):
        # We can maintain both an asyncpg pool and a supabase client if needed
        # depending on if the user prefers raw SQL vs supabase py API.
        # The prompt asked for "Supabase async connection" and specified asyncpg.
        # We also have the 'supabase-py' dependency. We'll set up both if appropriate.
        self.pool: Optional[asyncpg.Pool] = None
        self.supabase: Client = create_client(settings.supabase_url, settings.supabase_key)

    async def connect(self, dsn: str):
        self.pool = await asyncpg.create_pool(dsn=dsn)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

db = Database()

async def get_db_pool() -> asyncpg.Pool:
    if not db.pool:
        raise Exception("Database connection pool is not initialized")
    return db.pool
