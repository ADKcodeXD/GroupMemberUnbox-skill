import hashlib
import json
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests

from .schemas import IndexedMessage


KEYWORD_RULES = {
    "money": ["钱", "工资", "薪资", "穷", "氪", "消费", "买", "房租", "还款"],
    "work": ["上班", "下班", "工位", "公司", "老板", "同事", "加班", "bug", "需求", "会议"],
    "relationship": ["对象", "恋爱", "分手", "喜欢", "暧昧", "结婚", "前任", "女朋友", "男朋友"],
    "health": ["失眠", "熬夜", "头疼", "难受", "发烧", "医院", "健身", "焦虑", "累死"],
    "self_mock": ["废物", "菜", "蠢", "破防", "丢人", "小丑", "我真是", "麻了", "寄"],
    "attack": ["傻逼", "弱智", "有病", "恶心", "离谱", "笑死", "急了", "滚", "蠢货"],
    "help": ["帮我", "求", "怎么办", "有没有人", "教我", "救命", "求助"],
}


def normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _repetition_ratio(text: str) -> float:
    if not text:
        return 0.0
    windows = []
    for size in (2, 3, 4, 5, 6):
        if len(text) < size * 3:
            continue
        chunks = [text[i:i + size] for i in range(0, len(text) - size + 1, size)]
        if not chunks:
            continue
        most_common = max(chunks.count(chunk) for chunk in set(chunks))
        windows.append(most_common * size / max(1, len(text)))
    return round(max(windows) if windows else 0.0, 4)


def _unique_char_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return round(len(set(chars)) / len(chars), 4)


def make_msg_id(sender_uin: str, timestamp: int, text: str) -> str:
    base = f"{sender_uin}|{timestamp}|{text}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _safe_datetime(ts: int) -> Tuple[str, str, int]:
    raw_ts = ts or 0
    if raw_ts > 9999999999:
        raw_ts = int(raw_ts / 1000)
    dt = datetime.fromtimestamp(raw_ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d"), dt.hour


def compute_message_features(text: str, timestamp: int) -> Dict[str, Any]:
    normalized = normalize_text(text)
    exclamations = normalized.count("!") + normalized.count("！")
    questions = normalized.count("?") + normalized.count("？")
    ellipsis = normalized.count("...") + normalized.count("…")
    image_markers = normalized.count("[图片") + normalized.count("[表情") + normalized.count("[视频")
    is_forwarded = "xml version=" in normalized or "serviceID=" in normalized or "viewMultiMsg" in normalized
    repetition_ratio = _repetition_ratio(normalized)
    unique_char_ratio = _unique_char_ratio(normalized)
    repeated_phrase_hits = len(re.findall(r"(.{2,12}?)\1{2,}", normalized))
    raw_char_len = len(normalized)
    pure_text = re.sub(r"\[[^\]]+\]", "", normalized)
    pure_text_len = len(pure_text.strip())
    image_marker_density = round(image_markers / max(1, raw_char_len / 20), 4)
    emotion_score = min(1.0, (exclamations * 0.15) + (questions * 0.08) + (ellipsis * 0.06))
    if any(word in normalized for word in KEYWORD_RULES["attack"]):
        emotion_score = min(1.0, emotion_score + 0.25)
    punctuation_score = min(1.0, (exclamations + questions + ellipsis) / 6.0)
    late_night = False
    if timestamp:
        _, _, hour = _safe_datetime(timestamp)
        late_night = hour >= 23 or hour <= 5
    return {
        "char_len": len(normalized),
        "contains_money": any(word in normalized for word in KEYWORD_RULES["money"]),
        "contains_work": any(word in normalized for word in KEYWORD_RULES["work"]),
        "contains_relationship": any(word in normalized for word in KEYWORD_RULES["relationship"]),
        "contains_health": any(word in normalized for word in KEYWORD_RULES["health"]),
        "contains_self_mock": any(word in normalized for word in KEYWORD_RULES["self_mock"]),
        "contains_attack": any(word in normalized for word in KEYWORD_RULES["attack"]),
        "contains_help": any(word in normalized for word in KEYWORD_RULES["help"]),
        "punctuation_score": round(punctuation_score, 4),
        "emotion_score": round(emotion_score, 4),
        "late_night": late_night,
        "is_forwarded": is_forwarded,
        "image_markers": image_markers,
        "image_marker_density": image_marker_density,
        "repetition_ratio": repetition_ratio,
        "unique_char_ratio": unique_char_ratio,
        "repeated_phrase_hits": repeated_phrase_hits,
        "pure_text_len": pure_text_len,
    }


def build_message_index(messages: List[Dict[str, Any]], target_uin: str, context_window: int = 2) -> List[IndexedMessage]:
    indexed: List[IndexedMessage] = []
    for i, msg in enumerate(messages):
        text = (msg.get("content", {}) or {}).get("text", "")
        if not normalize_text(text) or msg.get("system", False):
            continue
        sender = msg.get("sender", {}) or {}
        sender_uin = str(sender.get("uin", ""))
        ts = int(msg.get("timestamp", 0) or 0)
        dt_text, date_text, hour = _safe_datetime(ts)
        before = []
        after = []
        for j in range(max(0, i - context_window), i):
            ctx = normalize_text((messages[j].get("content", {}) or {}).get("text", ""))
            if ctx:
                before.append(ctx)
        for j in range(i + 1, min(len(messages), i + context_window + 1)):
            ctx = normalize_text((messages[j].get("content", {}) or {}).get("text", ""))
            if ctx:
                after.append(ctx)
        normalized = normalize_text(text)
        indexed.append({
            "msg_id": make_msg_id(sender_uin, ts, normalized),
            "sender_uin": sender_uin,
            "sender_name": sender.get("name", "未知"),
            "timestamp": ts,
            "datetime": dt_text,
            "date": date_text,
            "hour": hour,
            "scene_tag": msg.get("scene_tag", "未知场景"),
            "is_target": sender_uin == str(target_uin),
            "text": normalized,
            "normalized_text": normalized,
            "context_before": before,
            "context_after": after,
            "features": compute_message_features(normalized, ts),
        })
    return indexed


def save_message_index(indexed_messages: List[IndexedMessage], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in indexed_messages:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_message_index(path: str) -> List[IndexedMessage]:
    items: List[IndexedMessage] = []
    if not path or not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def embed_texts_via_ollama(texts: List[str], config: Dict[str, Any]) -> List[List[float]]:
    model = config.get("embedding_model", "qwen3-embedding:0.6b")
    api_base = config.get("embedding_api_base", "http://localhost:11434").rstrip("/")
    url = f"{api_base}/api/embed"
    resp = requests.post(url, json={"model": model, "input": texts}, timeout=config.get("embedding_timeout", 120))
    resp.raise_for_status()
    data = resp.json()
    return data.get("embeddings", []) or []


def _tokenize_builtin(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []
    chars = [c for c in text if not c.isspace()]
    bigrams = [text[i:i+2] for i in range(len(text) - 1)]
    words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    return chars + bigrams + words


def _hash_to_dim(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dim


def embed_texts_builtin(texts: List[str], config: Dict[str, Any]) -> List[List[float]]:
    dim = int(config.get("builtin_embedding_dim", 384))
    outputs: List[List[float]] = []
    for text in texts:
        vec = [0.0] * dim
        tokens = _tokenize_builtin(text)
        for token in tokens:
            idx = _hash_to_dim(token, dim)
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        outputs.append(vec)
    return outputs


def ollama_model_exists(config: Dict[str, Any], model_name: str) -> bool:
    api_base = config.get("embedding_api_base", "http://localhost:11434").rstrip("/")
    url = f"{api_base}/api/tags"
    resp = requests.get(url, timeout=config.get("embedding_timeout", 120))
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models", []) or []
    existing_names = {item.get("name", "") for item in models}
    return model_name in existing_names


def ensure_ollama_model(config: Dict[str, Any], model_name: str) -> None:
    if ollama_model_exists(config, model_name):
        return

    if not config.get("auto_pull_local_models", True):
        raise RuntimeError(f"本地 Ollama 模型缺失，且未开启自动拉取: {model_name}")

    api_base = config.get("embedding_api_base", "http://localhost:11434").rstrip("/")
    url = f"{api_base}/api/pull"
    resp = requests.post(
        url,
        json={"name": model_name, "stream": False},
        timeout=max(300, config.get("embedding_timeout", 120)),
    )
    resp.raise_for_status()

    if not ollama_model_exists(config, model_name):
        raise RuntimeError(f"已尝试自动拉取，但本地仍未发现模型: {model_name}")


def ensure_specific_ollama_model(
    api_base: str,
    model_name: str,
    timeout: int = 120,
    auto_pull: bool = True,
) -> None:
    check_cfg = {
        "embedding_api_base": api_base,
        "embedding_timeout": timeout,
        "auto_pull_local_models": auto_pull,
    }
    if ollama_model_exists(check_cfg, model_name):
        return
    if not auto_pull:
        raise RuntimeError(f"本地 Ollama 模型缺失，且未开启自动拉取: {model_name}")
    url = f"{api_base.rstrip('/')}/api/pull"
    resp = requests.post(
        url,
        json={"name": model_name, "stream": False},
        timeout=max(300, timeout),
    )
    resp.raise_for_status()
    if not ollama_model_exists(check_cfg, model_name):
        raise RuntimeError(f"已尝试自动拉取，但本地仍未发现模型: {model_name}")


def embed_texts(texts: List[str], config: Dict[str, Any]) -> List[List[float]]:
    provider = config.get("embedding_provider", "builtin")
    if provider == "builtin":
        return embed_texts_builtin(texts, config)
    if provider == "ollama":
        model_name = config.get("embedding_model", "qwen3-embedding:0.6b")
        ensure_ollama_model(config, model_name)
        return embed_texts_via_ollama(texts, config)
    if provider == "remote_openai_compatible":
        model = config.get("embedding_model", "text-embedding-3-small")
        api_base = config.get("embedding_api_base", "").rstrip("/")
        api_key = config.get("embedding_api_key", "")
        if not api_base:
            raise RuntimeError("远程 embedding 缺少 API Base")
        if not api_key:
            raise RuntimeError("远程 embedding 缺少 API Key")
        url = f"{api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            url,
            headers=headers,
            json={"model": model, "input": texts},
            timeout=config.get("embedding_timeout", 120),
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", []) or []
        return [item.get("embedding", []) for item in items]
    raise RuntimeError(f"不支持的本地 embedding provider: {provider}")


def build_embeddings(indexed_messages: List[IndexedMessage], config: Dict[str, Any]) -> Dict[str, List[float]]:
    if not config.get("embedding_enabled", False):
        return {}
    texts = [item["normalized_text"] for item in indexed_messages]
    if not texts:
        return {}
    vectors = embed_texts(texts, config)
    out: Dict[str, List[float]] = {}
    for item, vec in zip(indexed_messages, vectors):
        out[item["msg_id"]] = vec
    return out


def save_embeddings(embeddings: Dict[str, List[float]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, ensure_ascii=False)


def load_embeddings(path: str) -> Dict[str, List[float]]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
