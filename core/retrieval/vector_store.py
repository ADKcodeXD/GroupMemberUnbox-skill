from typing import Dict, List, Optional

from .embed_index import cosine_similarity
from .schemas import IndexedMessage, RetrievalHit


def make_context_text(item: IndexedMessage) -> str:
    parts = []
    if item.get("context_before"):
        parts.append("\n".join(item["context_before"]))
    parts.append(item["text"])
    if item.get("context_after"):
        parts.append("\n".join(item["context_after"]))
    return "\n".join(parts)


def search_index(
    query_vector: List[float],
    indexed_messages: List[IndexedMessage],
    embeddings: Dict[str, List[float]],
    top_k: int = 8,
    target_only: bool = False,
) -> List[RetrievalHit]:
    scored: List[RetrievalHit] = []
    for item in indexed_messages:
        if target_only and not item.get("is_target", False):
            continue
        vec = embeddings.get(item["msg_id"])
        if not vec:
            continue
        score = cosine_similarity(query_vector, vec)
        if score <= 0:
            continue
        reasons = ["semantic_match"]
        features = item.get("features", {})
        if features.get("late_night"):
            reasons.append("late_night")
        if features.get("contains_self_mock"):
            reasons.append("self_mock")
        scored.append({
            "msg_id": item["msg_id"],
            "score": round(score, 4),
            "text": item["text"],
            "timestamp": item["timestamp"],
            "datetime": item["datetime"],
            "scene_tag": item["scene_tag"],
            "context": make_context_text(item),
            "hit_reason": reasons,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
