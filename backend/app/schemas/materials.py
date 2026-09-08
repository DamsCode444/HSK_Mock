from typing import Literal

from pydantic import BaseModel


class MaterialAccessRequest(BaseModel):
    disposition: Literal["inline", "attachment"] = "inline"


class MaterialAccessGrant(BaseModel):
    url: str
    expires_at: str
    filename: str
    media_type: str
    size_bytes: int
