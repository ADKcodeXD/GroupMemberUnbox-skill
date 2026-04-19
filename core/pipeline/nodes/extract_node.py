import os
from datetime import datetime
from ..state import AgentState
from ...data_processor import extract_chat_context, format_for_ai

def extract_node(state: AgentState) -> dict:
    """数据提取节点"""
    if state["stop_event"].is_set(): return {}
    
    cfg = state["config"]
    cb = state.get("callbacks", {})
    
    # 检查是否是恢复任务
    if state.get("chunks"):
        if "progress" in cb: cb["progress"](15, f"已恢复任务: 共 {len(state['chunks'])} 个切片")
        return {"current_stage": "Extract (Resumed)"}

    # 初始化日志目录 (如果还未初始化)
    if not state.get("session_log_dir"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_log_dir = os.path.abspath(f"logs/{state['target_uin']}-{timestamp}")
        os.makedirs(session_log_dir, exist_ok=True)
        state["session_log_dir"] = session_log_dir
    
    log_dir = state["session_log_dir"]
    
    messages = extract_chat_context(
        state["files"], state["target_uin"],
        cfg.get("only_target", False),
        cfg.get("sample_enabled", True),
        cfg.get("sample_limit", 5000),
        cfg.get("context_window", 2)
    )
    
    if not messages:
        return {"error": f"未能找到 QQ号为 {state['target_uin']} 的任何聊天记录。", "is_running": False}
        
    if "progress" in cb: cb["progress"](10, "正在进行 AI 适配格式化...")
    
    chat_text = format_for_ai(messages, state["target_uin"], cfg.get("only_target", False))
    if "preview" in cb: 
        p_text = chat_text[:3000] + ("..." if len(chat_text) > 3000 else "")
        cb["preview"]("raw_preview", p_text)
    
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
        "session_log_dir": log_dir,
        "progress": 15,
        "current_stage": "Extract"
    }
