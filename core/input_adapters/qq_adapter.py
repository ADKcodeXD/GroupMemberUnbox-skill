from typing import Any, Dict, List

from .base import NormalizedMessage, PlatformAdapter


class QQAdapter(PlatformAdapter):
    platform_name = "qq"

    def can_handle(self, data: Dict[str, Any], file_path: str) -> bool:
        if not isinstance(data, dict):
            return False
        if "messages" not in data:
            return False
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return False
        if not messages:
            return True
        sample = messages[0]
        return isinstance(sample, dict) and "sender" in sample and "content" in sample

    def normalize(self, data: Dict[str, Any], file_path: str) -> List[NormalizedMessage]:
        messages = data.get("messages", [])
        chat_info = data.get("chatInfo", {}) or {}
        chat_type = chat_info.get("type", "group")
        chat_name = chat_info.get("name", "未知")
        scene_tag = f"私聊-与{chat_name}对话" if chat_type == "private" else f"群聊-来自{chat_name}群"

        normalized: List[NormalizedMessage] = []
        for msg in messages:
            sender = msg.get("sender", {}) or {}
            content = msg.get("content", {}) or {}
            normalized.append({
                "timestamp": int(msg.get("timestamp", 0) or 0),
                "sender": {
                    "uin": str(sender.get("uin", "")),
                    "name": str(sender.get("name", "未知")),
                    "platform_id": str(sender.get("uin", "")),
                },
                "content": {
                    "text": str(content.get("text", "") or ""),
                },
                "system": bool(msg.get("system", False)),
                "scene_tag": scene_tag,
                "source_platform": self.platform_name,
                "source_file": file_path,
                "raw": msg,
            })
        return normalized
