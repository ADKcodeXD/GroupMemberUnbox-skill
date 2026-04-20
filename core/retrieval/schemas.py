from typing import TypedDict, List, Dict, Any


class IndexedMessage(TypedDict):
    msg_id: str
    sender_uin: str
    sender_name: str
    timestamp: int
    datetime: str
    date: str
    hour: int
    scene_tag: str
    is_target: bool
    text: str
    normalized_text: str
    context_before: List[str]
    context_after: List[str]
    features: Dict[str, Any]


class RetrievalHit(TypedDict):
    msg_id: str
    score: float
    text: str
    timestamp: int
    datetime: str
    scene_tag: str
    context: str
    hit_reason: List[str]


class HighlightCandidate(TypedDict):
    msg_id: str
    priority_score: float
    tags: List[str]
    representative: bool
    text: str
    context: str
    datetime: str
    scene_tag: str
