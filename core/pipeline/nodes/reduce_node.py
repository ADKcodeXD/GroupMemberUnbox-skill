import os
import concurrent.futures
from ..state import AgentState
from ..utils import read_prompt, call_ai, RateLimiter

def reduce_node(state: AgentState) -> dict:
    """Reduce 阶段节点：生成最终报告"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    evidence_base = state["evidence_base"]
    target_uin = state["target_uin"]
    
    # 聚合风味记录
    high_value_highlights = ""
    for i, res in enumerate(state["fidelity_results"]):
        if res and res.strip():
            high_value_highlights += f"--- 来自切片 {i+1} ---\n{res}\n\n"
    
    if not high_value_highlights.strip():
        high_value_highlights = "（未从切片提取到符合标准的高价值原始记录）"
        
    with open(os.path.join(state["session_log_dir"], "all_high_value_snippets.md"), "w", encoding="utf-8") as f:
        f.write(high_value_highlights)

    system_reduce_base = read_prompt("system_reduce.md")
    system_profiling = read_prompt("system_profiling.md")
    
    prompt_resume = read_prompt("prompt_resume.md").format(evidence_base=evidence_base, high_value_highlights=high_value_highlights, target_uin=target_uin)
    prompt_analysis = read_prompt("prompt_analysis.md").format(evidence_base=evidence_base, high_value_highlights=high_value_highlights, target_uin=target_uin)
    prompt_literary = read_prompt("prompt_literary.md").format(evidence_base=evidence_base, high_value_highlights=high_value_highlights, target_uin=target_uin)
    prompt_profiling = read_prompt("prompt_profiling.md").format(evidence_base=evidence_base, high_value_highlights=high_value_highlights, target_uin=target_uin)
    
    reduce_tasks = {
        "resume":    (prompt_resume,    system_reduce_base),
        "analysis":  (prompt_analysis,  system_reduce_base),
        "literary":  (prompt_literary,   system_reduce_base),
        "profiling": (prompt_profiling,  system_profiling),
    }
    
    reduce_results = {}
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    cb = state.get("callbacks", {})
    
    def run_task(key, p, s):
        res = call_ai(cfg, p, s, rate_limiter, stop_event)
        if "preview" in cb: cb["preview"](f"reduce_{key}", res)
        return key, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.get("reduce_workers", 4)) as executor:
        futures = {executor.submit(run_task, k, p, s): k for k, (p, s) in reduce_tasks.items()}
        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set(): break
            key, res = future.result()
            reduce_results[key] = res
            
    completed_modules = len(reduce_results)
    if "progress" in cb:
        p = 75 + int((completed_modules / 4) * 10)
        cb["progress"](p, f"正在生成终极档案... ({completed_modules}/4)")
            
    combined_report = f"# 人物档案总报告\n\n---\n\n# 📋 模块一：人物简历档案\n\n{reduce_results.get('resume', '')}\n\n---\n\n# 🔬 模块二：深度解剖报告\n\n{reduce_results.get('analysis', '')}\n\n---\n\n# 📖 模块三：文学叙事\n\n{reduce_results.get('literary', '')}\n\n---\n\n# 🧠 模块四：终极侧写报告\n\n{reduce_results.get('profiling', '')}"

    with open(os.path.join(state["session_log_dir"], "00_final_report.md"), "w", encoding="utf-8") as f:
        f.write(combined_report)
        
    return {
        "reduce_results": reduce_results,
        "combined_report": combined_report,
        "progress": 85,
        "current_stage": "Reduce"
    }
