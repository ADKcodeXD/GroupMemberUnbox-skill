import os
import re
import json
from datetime import datetime
from collections import Counter
import jieba
from ..state import AgentState
from ...data_processor import extract_chat_context, format_for_ai

import jieba.analyse
import jieba.posseg as pseg

# 互联网常用口癖与黑话字典 (防止被分词拆散)
SLANG_DICT = [
    "笑死", "好家伙", "确实", "麻了", "离谱", "针不戳", "这就是", "有一说一", 
    "坏了", "稳了", "急了", "典中典", "乐了", "流汗黄豆", "蚌埠住了"
]

# 更加严苛的系统词黑名单，彻底剔除元数据干扰
SYSTEM_STOPWORDS = [
    "群聊", "来自", "人物", "目标", "回复", "消息", "表情", "图片", "视频", "撤回", 
    "红包", "分享", "链接", "通话", "发送", "收到", "文件", "语音", "对方"
]

def calculate_word_frequency(text, target_uin, top_n=50):
    """进行深度词频与语感指纹分析"""
    # 1. 注入自定义字典
    for s in SLANG_DICT:
        jieba.add_word(s)

    # 2. 提取高权值特征词 (TF-IDF)
    # 增加黑名单过滤
    top_k = top_n + 20 # 多提一点用来过滤
    keywords = jieba.analyse.extract_tags(
        text, 
        topK=top_k, 
        withWeight=True, 
        allowPOS=('n', 'nr', 'ns', 'nz', 'v', 'vd', 'vn', 'a', 'ad', 'an', 'y', 'd')
    )
    
    filtered_keywords = []
    for k, w in keywords:
        if k in SYSTEM_STOPWORDS or k == target_uin:
            continue
        filtered_keywords.append({"word": k, "weight": round(w, 4)})
        if len(filtered_keywords) >= top_n: break

    # 3. 专项提取语气助词 (语气指纹)
    words = pseg.cut(text)
    particles = [w.word for w in words if w.flag == 'y' and len(w.word) >= 1]
    # 过滤单字常用词如“的”、“了”如果是归类为语气词的话（jieba有时会误判）
    particles = [p for p in particles if p not in ["的", "了", "是"]]
    particle_counts = Counter(particles).most_common(10)

    # 4. 组装结果
    analysis_report = {
        "top_keywords": filtered_keywords,
        "modal_particles": [{"word": p, "count": c} for p, c in particle_counts]
    }
    
    return analysis_report

def extract_node(state: AgentState) -> dict:
    """数据提取节点"""
    if state["stop_event"].is_set(): return {}
    
    cfg = state["config"]
    cb = state.get("callbacks", {})
    target_uin = state["target_uin"]
    
    # 检查是否是恢复任务
    if state.get("chunks"):
        if "progress" in cb: cb["progress"](15, f"已恢复任务: 共 {len(state['chunks'])} 个切片")
        return {"current_stage": "Extract (Resumed)"}

    # 初始化日志目录 (如果还未初始化)
    if not state.get("session_log_dir"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_log_dir = os.path.abspath(f"logs/{target_uin}-{timestamp}")
        os.makedirs(session_log_dir, exist_ok=True)
        state["session_log_dir"] = session_log_dir
    
    log_dir = state["session_log_dir"]
    
    messages = extract_chat_context(
        state["files"], target_uin,
        cfg.get("only_target", False),
        cfg.get("sample_enabled", True),
        cfg.get("sample_limit", 5000),
        cfg.get("context_window", 2)
    )
    
    if not messages:
        return {"error": f"未能找到 QQ号为 {target_uin} 的任何聊天记录。", "is_running": False}
        
    if "progress" in cb: cb["progress"](10, "正在进行 AI 适配格式化...")
    
    chat_text = format_for_ai(messages, target_uin, cfg.get("only_target", False))
    if "preview" in cb: 
        p_text = chat_text[:3000] + ("..." if len(chat_text) > 3000 else "")
        cb["preview"]("raw_preview", p_text)
    
    # --- 新增：词频统计 (优化：仅分析目标人物的原始发言内容) ---
    if "progress" in cb: cb["progress"](12, "正在进行‘神魂捕获’语言分析...")
    
    target_only_text = "\n".join([
        m.get("content", {}).get("text", "") 
        for m in messages 
        if str(m.get("sender", {}).get("uin", "")) == str(target_uin)
    ])
    
    word_freq = calculate_word_frequency(target_only_text, target_uin)
    
    if "preview" in cb:
        kw_list = [f"{k['word']}({k['weight']})" for k in word_freq.get("top_keywords", [])]
        pt_list = [f"{p['word']}({p['count']})" for p in word_freq.get("modal_particles", [])]
        stats_text = (
            f"### 🔍 核心语言指纹分析完成\n\n"
            f"**🔥 高权特征词**：\n> {', '.join(kw_list[:20])}\n\n"
            f"**🗣️ 语气助词偏向**：\n> {', '.join(pt_list)}\n\n"
            f"*以上数据已注入炼化炉，用于校准 AI 模拟语感。*"
        )
        cb["preview"]("extract_stats", stats_text)

    with open(os.path.join(log_dir, "01a_word_frequency.json"), "w", encoding="utf-8") as f:
        json.dump(word_freq, f, ensure_ascii=False, indent=4)
    # --- 结束：词频统计 ---

    # 保存完整文本
    with open(os.path.join(log_dir, "full_chat_text.txt"), "w", encoding="utf-8") as f:
        f.write(chat_text)
    
    # 分段
    chunk_size = cfg.get("chunk_size", 100000)
    chunks = [chat_text[i:i+chunk_size] for i in range(0, len(chat_text), chunk_size)]
    
    # 保存原始分块以备断点续传 (确保切分一致性)
    chunk_dir = os.path.join(log_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)
    for i, c in enumerate(chunks):
        with open(os.path.join(chunk_dir, f"chunk_{i+1}.txt"), "w", encoding="utf-8") as f:
            f.write(c)
            
    if "progress" in cb: cb["progress"](15, f"数据提取完成，共分 {len(chunks)} 个切片")
    
    return {
        "messages": messages,
        "chat_text": chat_text,
        "chunks": chunks,
        "map_results": [None] * len(chunks),
        "fidelity_results": [None] * len(chunks),
        "word_frequency": word_freq, # 将词频注入状态
        "session_log_dir": log_dir,
        "progress": 15,
        "current_stage": "Extract"
    }
