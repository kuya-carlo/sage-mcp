from pydantic import BaseModel
from datetime import datetime

class UserToken(BaseModel):
    workspace_id: str
    encrypted_token: str
    bot_id: str
    created_at: datetime
    updated_at: datetime
