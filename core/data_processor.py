import datetime
import re
from collections import defaultdict
from typing import List

from .input_adapters.registry import load_normalized_messages


def extract_chat_context(files, target_uin, only_target=False, sample=False, sample_limit=5000, context_window=2):
    all_target_indices_by_file = []

    for file_path in files:
        try:
            messages = load_normalized_messages(file_path)
            target_indices = []
            for i, msg in enumerate(messages):
                sender_uin = str((msg.get("sender", {}) or {}).get("uin", ""))
                if sender_uin == str(target_uin) and not msg.get("system", False):
                    target_indices.append(i)
            all_target_indices_by_file.append((file_path, messages, target_indices))
        except Exception as e:
            print(f"处理文件 {file_path} 失败: {e}")

    all_target_msgs = []
    for file_path, messages, target_indices in all_target_indices_by_file:
        for idx in target_indices:
            msg = messages[idx]
            ts = msg.get("timestamp", 0)
            text_len = len(((msg.get("content", {}) or {}).get("text", "")))
            all_target_msgs.append({
                "file_path": file_path,
                "msg_idx": idx,
                "ts": ts,
                "len": text_len,
                "scene_tag": msg.get("scene_tag", "未知场景"),
                "messages": messages,
            })

    all_target_msgs.sort(key=lambda x: x["ts"])

    selected_target_msgs = []
    if sample and len(all_target_msgs) > sample_limit:
        bucket_size = len(all_target_msgs) / sample_limit
        for i in range(sample_limit):
            start = int(i * bucket_size)
            end = int((i + 1) * bucket_size)
            bucket = all_target_msgs[start:end]
            if bucket:
                best_msg = max(bucket, key=lambda x: x["len"])
                selected_target_msgs.append(best_msg)
    else:
        selected_target_msgs = all_target_msgs

    indices_to_add_by_file = defaultdict(set)
    for item in selected_target_msgs:
        idx = item["msg_idx"]
        file_path = item["file_path"]

        if only_target:
            indices_to_add_by_file[file_path].add(idx)
        else:
            messages = item["messages"]
            for offset in range(-context_window, context_window + 1):
                neighbor = idx + offset
                if 0 <= neighbor < len(messages):
                    indices_to_add_by_file[file_path].add(neighbor)
            indices_to_add_by_file[file_path].add(idx)

    extracted_messages = []
    for file_path, messages, _ in all_target_indices_by_file:
        if file_path not in indices_to_add_by_file:
            continue
        for idx in sorted(list(indices_to_add_by_file[file_path])):
            msg_copy = dict(messages[idx])
            msg_copy["source_file"] = file_path
            extracted_messages.append(msg_copy)

    extracted_messages.sort(key=lambda x: x.get("timestamp", 0))
    return extracted_messages


def format_for_ai(extracted_messages, target_uin, only_target=False):
    lines = []
    for msg in extracted_messages:
        ts = msg.get("timestamp", 0)
        if ts > 9999999999:
            ts = ts / 1000.0

        dt = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        scene_tag = msg.get("scene_tag", "未知场景")
        sender = msg.get("sender", {}) or {}
        sender_name = sender.get("name", "未知")
        sender_uin_msg = str(sender.get("uin", ""))

        if only_target:
            role = ""
        else:
            role = "【目标人物】" if sender_uin_msg == str(target_uin) else ""

        content = (msg.get("content", {}) or {}).get("text", "")

        if not content.strip() or len(content.strip()) == 1 or msg.get("system", False):
            continue

        line = f"[{dt}] 【{scene_tag}】 {role}{sender_name}({sender_uin_msg}): {content}"
        lines.append(line)

    return "\n".join(lines)
