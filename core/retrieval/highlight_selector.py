import json
from typing import Dict, List, Tuple

from .embed_index import cosine_similarity
from .schemas import HighlightCandidate, IndexedMessage
from .vector_store import make_context_text


def _noise_penalty(item: IndexedMessage) -> Tuple[float, List[str]]:
    features = item.get("features", {})
    text = (item.get("text") or "").strip()
    penalty = 0.0
    flags: List[str] = []

    repetition_ratio = float(features.get("repetition_ratio", 0.0))
    unique_char_ratio = float(features.get("unique_char_ratio", 1.0))
    repeated_phrase_hits = int(features.get("repeated_phrase_hits", 0))
    image_markers = int(features.get("image_markers", 0))
    image_marker_density = float(features.get("image_marker_density", 0.0))
    pure_text_len = int(features.get("pure_text_len", len(text)))
    is_forwarded = bool(features.get("is_forwarded", False))

    if is_forwarded:
        penalty += 1.8
        flags.append("forwarded")
    if repetition_ratio >= 0.35:
        penalty += 1.8
        flags.append("repetition")
    elif repetition_ratio >= 0.2:
        penalty += 0.9
        flags.append("repetition")
    if repeated_phrase_hits >= 1:
        penalty += min(1.2, repeated_phrase_hits * 0.45)
        flags.append("repeated_phrase")
    if unique_char_ratio <= 0.22 and len(text) >= 40:
        penalty += 0.9
        flags.append("low_diversity")
    if image_markers >= 3 or image_marker_density >= 1.2:
        penalty += 1.0
        flags.append("media_heavy")
    if pure_text_len <= 8 and len(text) >= 20:
        penalty += 0.9
        flags.append("low_text_signal")

    return round(penalty, 4), flags


def _base_score(item: IndexedMessage) -> Tuple[float, List[str]]:
    score = 0.0
    tags: List[str] = []
    features = item.get("features", {})
    if not item.get("is_target", False):
        return 0.0, tags

    length = features.get("char_len", 0)
    score += min(1.5, length / 60.0)
    if features.get("contains_self_mock"):
        score += 1.2
        tags.append("self_mock")
    if features.get("contains_attack"):
        score += 1.1
        tags.append("attack")
    if features.get("contains_help"):
        score += 1.0
        tags.append("help")
    if features.get("contains_work"):
        score += 0.7
        tags.append("work")
    if features.get("contains_relationship"):
        score += 0.8
        tags.append("relationship")
    if features.get("contains_money"):
        score += 0.6
        tags.append("money")
    if features.get("contains_health"):
        score += 0.7
        tags.append("health")
    if features.get("late_night"):
        score += 0.6
        tags.append("late_night")
    score += float(features.get("emotion_score", 0))
    score += float(features.get("punctuation_score", 0)) * 0.5
    penalty, penalty_flags = _noise_penalty(item)
    score -= penalty
    for flag in penalty_flags:
        tags.append(f"noise:{flag}")
    return round(score, 4), tags


def select_high_value_candidates(
    indexed_messages: List[IndexedMessage],
    embeddings: Dict[str, List[float]],
    candidate_limit: int = 300,
    max_output: int = 50,
) -> List[HighlightCandidate]:
    prelim: List[HighlightCandidate] = []
    for item in indexed_messages:
        score, tags = _base_score(item)
        feature_map = item.get("features", {})
        if score <= 0:
            continue
        if feature_map.get("is_forwarded"):
            continue
        if float(feature_map.get("repetition_ratio", 0.0)) >= 0.42:
            continue
        if int(feature_map.get("image_markers", 0)) >= 5:
            continue
        if int(feature_map.get("pure_text_len", 0)) <= 6 and len(item.get("text", "")) >= 24:
            continue
        prelim.append(
            {
                "msg_id": item["msg_id"],
                "priority_score": score,
                "tags": tags,
                "representative": False,
                "text": item["text"],
                "context": make_context_text(item),
                "datetime": item["datetime"],
                "scene_tag": item["scene_tag"],
            }
        )
    prelim.sort(key=lambda x: x["priority_score"], reverse=True)
    prelim = prelim[:candidate_limit]

    if not embeddings:
        for i, item in enumerate(prelim[:max_output]):
            item["representative"] = i < 20
        return prelim[:max_output]

    selected: List[HighlightCandidate] = []
    used_vectors: List[List[float]] = []
    for cand in prelim:
        vec = embeddings.get(cand["msg_id"])
        if not vec:
            continue
        if not used_vectors:
            cand["representative"] = True
            selected.append(cand)
            used_vectors.append(vec)
        else:
            max_sim = max(cosine_similarity(vec, existing) for existing in used_vectors)
            mmr_score = cand["priority_score"] - (max_sim * 1.2)
            if mmr_score > 0.55 or len(selected) < min(15, max_output):
                cand["representative"] = len(selected) < 20
                selected.append(cand)
                used_vectors.append(vec)
        if len(selected) >= max_output:
            break

    if len(selected) < min(20, max_output):
        fallback_ids = {item["msg_id"] for item in selected}
        for cand in prelim:
            if cand["msg_id"] in fallback_ids:
                continue
            selected.append(cand)
            if len(selected) >= max_output:
                break

    return selected[:max_output]


def _trim_text(text: str, limit: int = 220) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def select_chunk_candidates(
    candidates: List[HighlightCandidate],
    chunk: str,
    min_items: int = 30,
    max_items: int = 50,
) -> List[HighlightCandidate]:
    if not candidates:
        return []

    related: List[HighlightCandidate] = []
    fallback: List[HighlightCandidate] = []

    for item in candidates:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if text in chunk:
            related.append(item)
        else:
            fallback.append(item)

    selected = related[:max_items]
    if len(selected) < min_items:
        seen_ids = {item["msg_id"] for item in selected}
        for item in fallback:
            if item["msg_id"] in seen_ids:
                continue
            selected.append(item)
            if len(selected) >= max_items:
                break

    return selected[:max_items]


def format_fidelity_candidates_markdown(
    candidates: List[HighlightCandidate],
    max_context_chars: int = 380,
) -> str:
    if not candidates:
        return "无可用候选。"

    lines: List[str] = []
    for i, item in enumerate(candidates, 1):
        target_text = _trim_text(item.get("text", ""), 180)
        context_summary = _trim_text(item.get("context", ""), max_context_chars)
        tags = ", ".join(item.get("tags", [])) or "generic"
        lines.append(
            f"### C{i}\n"
            f"- 时间: {item.get('datetime', '')}\n"
            f"- 场景: {item.get('scene_tag', '')}\n"
            f"- 标签: {tags}\n"
            f"- 分数: {item.get('priority_score', 0)}\n"
            f"- 目标人物对话: {target_text}\n"
            f"- 上下文摘要: {context_summary}\n"
            f"- 原始上下文:\n{item.get('context', '').strip()}"
        )
    return "\n\n".join(lines)


def format_highlights_markdown(candidates: List[HighlightCandidate]) -> str:
    lines = []
    for i, item in enumerate(candidates, 1):
        tag_text = ", ".join(item.get("tags", [])) or "generic"
        lines.append(
            f"### H{i} | {item['datetime']} | {item['scene_tag']} | tags={tag_text} | score={item['priority_score']}\n"
            f"> {item['text']}\n\n"
            f"上下文：\n{item['context']}"
        )
    return "\n\n".join(lines)


def save_candidates_jsonl(candidates: List[HighlightCandidate], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in candidates:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
