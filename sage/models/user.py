from datetime import datetime

from pydantic import BaseModel


class UserToken(BaseModel):
    workspace_id: str
    encrypted_token: str
    bot_id: str
    created_at: datetime
    updated_at: datetime
