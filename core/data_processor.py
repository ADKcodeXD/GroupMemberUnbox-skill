import os
import json
import datetime
import re

def extract_chat_context(files, target_uin, only_target=False, sample=False, sample_limit=5000, context_window=2):
    all_target_indices_by_file = []
    
    for file_path in files:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            messages = data.get("messages", [])
            target_indices = []
            for i, msg in enumerate(messages):
                sender_uin = msg.get("sender", {}).get("uin", "")
                if sender_uin == target_uin and not msg.get("system", False):
                    target_indices.append(i)
            all_target_indices_by_file.append((file_path, data, target_indices))
        except Exception as e:
            print(f"处理文件 {file_path} 失败: {e}")

    # 收集所有目标人物的消息以供抽样
    all_target_msgs = []
    for file_path, data, target_indices in all_target_indices_by_file:
        messages = data.get("messages", [])
        chat_info = data.get("chatInfo", {})
        chat_type = chat_info.get("type", "group")
        chat_name = chat_info.get("name", "未知")
        scene_tag = f"私聊-与{chat_name}对话" if chat_type == "private" else f"群聊-来自{chat_name}群"
        
        for idx in target_indices:
            msg = messages[idx]
            ts = msg.get("timestamp", 0)
            text_len = len(msg.get("content", {}).get("text", ""))
            all_target_msgs.append({
                "file_path": file_path,
                "msg_idx": idx,
                "ts": ts,
                "len": text_len,
                "scene_tag": scene_tag,
                "messages": messages
            })

    # 全局按时间戳排序
    all_target_msgs.sort(key=lambda x: x["ts"])
    
    selected_target_msgs = []
    if sample and len(all_target_msgs) > sample_limit:
        # 分桶均匀抽样：按数量等分为 sample_limit 个桶，每个桶里挑字数最多的
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

    # 提取选中的消息及上下文
    from collections import defaultdict
    indices_to_add_by_file = defaultdict(set)
    file_scene_tag = {}
    
    for item in selected_target_msgs:
        idx = item["msg_idx"]
        file_path = item["file_path"]
        file_scene_tag[file_path] = item["scene_tag"]
        
        if only_target:
            indices_to_add_by_file[file_path].add(idx)
        else:
            messages = item["messages"]
            # 上下各取 context_window 条作为上下文
            for offset in range(-context_window, context_window + 1):
                neighbor = idx + offset
                if 0 <= neighbor < len(messages):
                    indices_to_add_by_file[file_path].add(neighbor)
            indices_to_add_by_file[file_path].add(idx)

    extracted_messages = []
    for file_path, data, _ in all_target_indices_by_file:
        if file_path not in indices_to_add_by_file:
            continue
        messages = data.get("messages", [])
        scene_tag = file_scene_tag.get(file_path, "未知场景")
        for idx in sorted(list(indices_to_add_by_file[file_path])):
            msg_copy = messages[idx].copy()
            msg_copy["scene_tag"] = scene_tag
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
        sender_name = msg.get("sender", {}).get("name", "未知")
        sender_uin_msg = msg.get("sender", {}).get("uin", "")
        
        if only_target:
            role = ""
        else:
            role = "【目标人物】" if sender_uin_msg == target_uin else ""
        
        content = msg.get("content", {}).get("text", "")
        
        # 不再剔除 [图片], [视频] 等占位符，保留它们作为上下文语境，帮助 AI 理解目标人物是否在解释图片内容
        # content = re.sub(r'\[图片.*?\]', '', content)
        # content = re.sub(r'\[视频.*?\]', '', content)
        
        # 过滤掉空消息、系统消息、以及剔除占位符后仅有 1 个字符的无意义单字回复
        if not content.strip() or len(content.strip()) == 1 or msg.get("system", False):
            continue
            
        line = f"[{dt}] 【{scene_tag}】 {role}{sender_name}({sender_uin_msg}): {content}"
        lines.append(line)
        
    return "\n".join(lines)
