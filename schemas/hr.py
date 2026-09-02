from typing import Optional, List

from pydantic import BaseModel


# ============================================================
# HR CHAT REQUEST
# ============================================================

class HRChatRequest(BaseModel):

    message: str

    candidate_id: Optional[int] = None

    conversation_id: Optional[int] = None


# ============================================================
# HR SOURCE
# ============================================================

class HRSource(BaseModel):

    candidate_id: int

    candidate_name: str

    section: Optional[str] = None

    content: str

    chunk_id: int

    score: Optional[float] = None


# ============================================================
# HR RESPONSE
# ============================================================

class HRChatResponse(BaseModel):

    answer: str

    conversation_id: int

    sources: List[HRSource]