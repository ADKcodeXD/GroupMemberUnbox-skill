import os
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
    prompt_merge = prompt_merge_tpl.format(raw_map_text=raw_map_text, target_uin=state["target_uin"])
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    evidence_base = call_ai(cfg, prompt_merge, system_merge, rate_limiter, stop_event)
    
    # 保存结果
    with open(os.path.join(state["session_log_dir"], "evidence_base_draft.md"), "w", encoding="utf-8") as f:
        f.write(evidence_base)
        
    return {
        "evidence_base": evidence_base,
        "current_stage": "Merge (Draft)",
        "progress": 70
    }

def audit_node(state: AgentState) -> dict:
    """审计节点 (Agent Mode 专用)"""
    stop_event = state["stop_event"]
    if stop_event.is_set() or not state["config"].get("agent_mode", False):
        return {"audit_opinion": "【审计跳过】", "audit_count": state.get("audit_count", 0)}
    
    cfg = state["config"]
    evidence_base = state["evidence_base"]
    audit_count = state.get("audit_count", 0) + 1
    
    # 准备参考上下文: 选取部分精选摘要和知识点进行对比
    highlights_context = "\n".join([r for r in state["fidelity_results"] if r][:10]) # 取前10个精选摘要
    knowledge_context = "\n".join([r for r in state["map_results"] if r][:5]) # 取前5个分段知识点
    
    system_review = read_prompt("system_review.md")
    prompt_audit = f"""
请审计以下初步生成的证据库（这是第 {audit_count} 轮审计）。
你的任务是核对证据库是否真实扎根于原始聊天记录，是否存在“脑补”或“遗漏”。

【待审计证据库】：
{evidence_base}

【参考原始摘要（精选）】：
{highlights_context}

【参考分段知识提取】：
{knowledge_context}

请对比上述参考资料，指出证据库中的漏洞、不自洽点或未被记录的重要特征。
如果认为已经足够完善，请务必在开头回复“【审计通过】”。
"""
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    audit_opinion = call_ai(cfg, prompt_audit, system_review, rate_limiter, stop_event)
    
    cb = state.get("callbacks", {})
    if "preview" in cb: cb["preview"]("evidence_base", f"### 🛡️ Agent 审计中...\n\n{audit_opinion}")
    
    with open(os.path.join(state["session_log_dir"], f"audit_opinion_v{audit_count}.md"), "w", encoding="utf-8") as f:
        f.write(audit_opinion)
        
    return {
        "audit_opinion": audit_opinion,
        "audit_count": audit_count,
        "current_stage": f"Merge (Audit Round {audit_count})",
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
