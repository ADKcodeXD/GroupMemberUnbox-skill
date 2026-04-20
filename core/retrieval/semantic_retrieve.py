import json
import os
from typing import Any, Dict, List, Tuple

from .embed_index import embed_texts, load_embeddings, load_message_index
from .vector_store import search_index


def semantic_retrieve(
    query: str,
    message_index_path: str,
    embedding_path: str,
    config: Dict[str, Any],
    top_k: int = 8,
    target_only: bool = False,
) -> Tuple[List[Dict[str, Any]], str]:
    if not query or not message_index_path or not embedding_path:
        return [], "【语义检索不可用：缺少索引或查询】"
    indexed_messages = load_message_index(message_index_path)
    embeddings = load_embeddings(embedding_path)
    if not indexed_messages or not embeddings:
        return [], "【语义检索不可用：索引为空】"
    query_vecs = embed_texts([query], config)
    query_vec = query_vecs[0] if query_vecs else []
    hits = search_index(query_vec, indexed_messages, embeddings, top_k=top_k, target_only=target_only)
    if not hits:
        return [], "【未找到语义匹配结果】。"
    parts = []
    for i, hit in enumerate(hits, 1):
        parts.append(
            f"--- 语义命中 {i} | score={hit['score']} | {hit['datetime']} | {hit['scene_tag']} ---\n"
            f"{hit['context']}"
        )
    return hits, "\n\n".join(parts)


def save_retrieval_json(hits: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hits, f, ensure_ascii=False, indent=2)
