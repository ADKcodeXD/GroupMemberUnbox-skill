from typing import Any, Dict, List, Optional, TypedDict


class NormalizedSender(TypedDict):
    uin: str
    name: str
    platform_id: str


class NormalizedContent(TypedDict):
    text: str


class NormalizedMessage(TypedDict):
    timestamp: int
    sender: NormalizedSender
    content: NormalizedContent
    system: bool
    scene_tag: str
    source_platform: str
    source_file: str
    raw: Dict[str, Any]


class PlatformAdapter:
    """平台聊天记录适配器基类。"""

    platform_name = "unknown"

    def can_handle(self, data: Dict[str, Any], file_path: str) -> bool:
        raise NotImplementedError

    def normalize(self, data: Dict[str, Any], file_path: str) -> List[NormalizedMessage]:
        raise NotImplementedError
