import json
import os
from typing import Dict, List

from .base import NormalizedMessage, PlatformAdapter
from .qq_adapter import QQAdapter


ADAPTERS: List[PlatformAdapter] = [
    QQAdapter(),
]


def detect_adapter(data: Dict, file_path: str) -> PlatformAdapter:
    for adapter in ADAPTERS:
        if adapter.can_handle(data, file_path):
            return adapter
    raise ValueError(f"未找到可处理文件的适配器: {file_path}")


def load_normalized_messages(file_path: str) -> List[NormalizedMessage]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    adapter = detect_adapter(data, file_path)
    return adapter.normalize(data, file_path)
