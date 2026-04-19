import os
import json
import re
from ..state import AgentState
from ..utils import read_prompt, call_ai, RateLimiter

def merge_node(state: AgentState) -> dict:
    """初始叠加汇总节点"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    map_results = state["map_results"]
    
    raw_map_text = "\n\n============== 时间切片分隔线 ==============\n\n".join(
        [f"【切片 {i+1} 提取结果】\n{text}" for i, text in enumerate(map_results)]
    )
    
    system_merge = read_prompt("system_merge.md")
    prompt_merge_tpl = read_prompt("prompt_merge.md")
    word_freq_text = json.dumps(state.get("word_frequency", []), ensure_ascii=False)
    prompt_merge = prompt_merge_tpl.format(
        raw_map_text=raw_map_text, 
        target_uin=state["target_uin"],
        word_frequency=word_freq_text
    )
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    evidence_base = call_ai(cfg, prompt_merge, system_merge, rate_limiter, stop_event)
    
    # 保存结果
    with open(os.path.join(state["session_log_dir"], "evidence_base_draft.md"), "w", encoding="utf-8") as f:
        f.write(evidence_base)
        
    return {
        "evidence_base": evidence_base,
        "current_stage": "Merge (Draft)",
        "progress": 70,
        "audit_count": 0,
        "tool_count": 0
    }

def retrieve_node(state: AgentState) -> dict:
    """检索工具节点: 在原始聊天记录中搜索关键词"""
    query = state.get("search_query")
    if not query:
        return {"search_results": "【错误】：未提供搜索关键词。"}
    
    chat_text = state.get("chat_text", "")
    lines = chat_text.split("\n")
    results = []
    
    # 限制检索结果数量
    max_hits = 10
    window = 5 # 上下文行数
    
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except Exception as e:
        return {"search_results": f"【错误】：正则表达式语法错误 - {e}"}
        
    hit_count = 0
    for i, line in enumerate(lines):
        if pattern.search(line):
            hit_count += 1
            start = max(0, i - window)
            end = min(len(lines), i + window + 1)
            context = "\n".join(lines[start:end])
            results.append(f"--- 搜索命中 {hit_count} (行 {i+1}) ---\n{context}")
            if hit_count >= max_hits: break
            
    res_text = "\n\n".join(results) if results else "【未找到匹配项】。"
    
    # 将结果保存到日志
    with open(os.path.join(state["session_log_dir"], f"search_{state['tool_count']}.md"), "w", encoding="utf-8") as f:
        f.write(f"Query: {query}\n\nResults:\n{res_text}")
        
    return {
        "search_results": res_text,
        "search_query": None, # 重置 query
        "current_stage": f"Retrieve (Tool Call {state['tool_count']})",
        "progress": state.get("progress", 70)
    }

def audit_node(state: AgentState) -> dict:
    """审计节点 (Agent Mode 专用)"""
    stop_event = state["stop_event"]
    if stop_event.is_set() or not state["config"].get("agent_mode", False):
        return {"audit_opinion": "【审计跳过】", "audit_count": state.get("audit_count", 0)}
    
    cfg = state["config"]
    evidence_base = state["evidence_base"]
    # 只有在没有搜索结果的情况下，才增加审计轮数 (搜索中不计入审计轮数)
    audit_count = state.get("audit_count", 0) + (1 if not state.get("search_results") else 0)
    tool_count = state.get("tool_count", 0)
    
    # 准备参考上下文
    highlights_context = "\n".join([r for r in state["fidelity_results"] if r][:10])
    knowledge_context = "\n".join([r for r in state["map_results"] if r][:5])
    
    system_review = read_prompt("system_review.md")
    
    # 如果有搜索结果，将其加入 Prompt
    search_context = ""
    if state.get("search_results"):
        search_context = f"\n\n【最新检索工具返回结果】：\n{state['search_results']}\n"
    
    prompt_audit = f"""
请审计以下初步生成的证据库。这是第 {audit_count} 轮审计（当前工具调用总数: {tool_count}）。
你的任务是核对证据库是否真实扎根于原始聊天记录。

{search_context}

【待审计证据库】：
{evidence_base}

【参考原始摘要（精选）】：
{highlights_context}

【参考分段知识提取】：
{knowledge_context}

---
指令：
1. 如果你需要搜索具体的原始聊天证据（如具体的日期、QQ号提及的内容、特定的词汇），请在回复中包含 `[SEARCH: 你的关键词或正则]` 标签。
2. 如果指出证据库中的漏洞，请列出具体的修改意见。
3. 如果认为已经足够完善，请务必在开头回复“【审计通过】”。
"""
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    audit_opinion = call_ai(cfg, prompt_audit, system_review, rate_limiter, stop_event)
    
    # 处理搜索请求
    search_query = None
    search_match = re.search(r'\[SEARCH:\s*(.*?)\]', audit_opinion)
    if search_match and tool_count < 5: # 限制最大工具链长度
        search_query = search_match.group(1).strip()
        tool_count += 1
    
    cb = state.get("callbacks", {})
    if "preview" in cb: cb["preview"]("evidence_base", f"### 🛡️ Agent 审计/检索中...\n\n{audit_opinion}")
    
    with open(os.path.join(state["session_log_dir"], f"audit_opinion_v{audit_count}_{tool_count}.md"), "w", encoding="utf-8") as f:
        f.write(audit_opinion)
        
    return {
        "audit_opinion": audit_opinion,
        "audit_count": audit_count,
        "tool_count": tool_count,
        "search_query": search_query,
        "search_results": None if search_query else state.get("search_results"), # 如果进入搜索，清空旧结果
        "current_stage": f"Merge (Audit R{audit_count} T{tool_count})",
        "progress": 70 + audit_count
    }

def refine_node(state: AgentState) -> dict:
    """基于审计意见的修正节点"""
    stop_event = state["stop_event"]
    if stop_event.is_set() or not state["config"].get("agent_mode", False):
        return {}
        
    if "【审计通过" in (state["audit_opinion"] or ""):
        return {"current_stage": "Merge (Final)"}

    cfg = state["config"]
    system_merge = read_prompt("system_merge.md")
    prompt_refine = f"""
你之前生成了人物证据库，但经过审计发现了一些问题（第 {state['audit_count']} 轮审计反馈）。
请根据以下审计意见对证据库进行修正：

【初步证据库】：
{state["evidence_base"]}

【审计意见】：
{state["audit_opinion"]}

任务：请输出一份修正后的、更加严谨的全景证据库。
"""
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    final_evidence = call_ai(cfg, prompt_refine, system_merge, rate_limiter, stop_event)
    
    cb = state.get("callbacks", {})
    if "preview" in cb: cb["preview"]("evidence_base", f"### ✨ Agent 已优化证据库\n\n{final_evidence}")
    
    with open(os.path.join(state["session_log_dir"], f"evidence_base_v{state['audit_count']}.md"), "w", encoding="utf-8") as f:
        f.write(final_evidence)
        
    return {
        "evidence_base": final_evidence,
        "current_stage": f"Merge (Refined v{state['audit_count']})",
        "progress": 72
    }
