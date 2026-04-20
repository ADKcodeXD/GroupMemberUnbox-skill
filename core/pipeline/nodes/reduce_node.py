import os
import json
import concurrent.futures
from ..state import AgentState
from ..utils import (
    read_prompt,
    call_ai,
    RateLimiter,
    parse_structured_prompt_sections,
    render_prompt_template,
)

def reduce_node(state: AgentState) -> dict:
    """Reduce 阶段节点：直接生成 6 层高保真灵魂模块"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    evidence_base = state["evidence_base"]
    target_uin = state["target_uin"]
    log_dir = state["session_log_dir"]
    
    # 聚合风味记录
    high_value_highlights = ""
    for i, res in enumerate(state["fidelity_results"]):
        if res and res.strip():
            high_value_highlights += f"--- 分片 {i+1} 原始素材 ---\n{res}\n\n"
    if not high_value_highlights.strip():
        high_value_highlights = "（未从切片提取到符合标准的高价值原始记录）"
    
    # 1. 深度保存中间证据到 LOG 目录 (不再污染根目录)
    with open(os.path.join(log_dir, "02_evidence_base.md"), "w", encoding="utf-8") as f: f.write(evidence_base)
    with open(os.path.join(log_dir, "01_high_value_snippets.md"), "w", encoding="utf-8") as f: f.write(high_value_highlights)

    # 2. 读取结构化 Prompt (Layered Architecture)
    try:
        skill_prompts_raw = read_prompt("prompt_skill.md")
        prompts = parse_structured_prompt_sections(skill_prompts_raw)
    except Exception as e:
        return {"error": f"加载 prompt_skill.md 失败: {str(e)}"}

    system_main = prompts.get("SYSTEM", "")
    shared_rules = "\n\n".join(filter(None, [
        "### [GLOBAL_EVIDENCE_PROTOCOL]\n" + prompts.get("GLOBAL_EVIDENCE_PROTOCOL", ""),
        "### [HIGH_RISK_INFERENCE_GUARDRAILS]\n" + prompts.get("HIGH_RISK_INFERENCE_GUARDRAILS", ""),
        "### [EVOLUTION_PRINCIPLES]\n" + prompts.get("EVOLUTION_PRINCIPLES", ""),
    ])).strip()
    input_block = render_prompt_template(
        prompts.get("INPUT", ""),
        target_uin=target_uin,
        evidence_base=evidence_base,
        high_value_highlights=high_value_highlights[:15000],
    )

    reduce_tasks = {
        "objective": prompts.get("LAYER_1_OBJECTIVE", ""),
        "inference": prompts.get("LAYER_2_INFERENCE", ""),
        "behavior":  prompts.get("LAYER_3_BEHAVIOR", ""),
        "memory":    prompts.get("LAYER_5_MEMORY", ""),
        "style":     prompts.get("LAYER_6_STYLE", "")
    }
    
    reduce_results = {}
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    cb = state.get("callbacks", {})
    
    def run_task(key, task_prompt):
        full_p = "\n\n".join(filter(None, [
            f"目标角色：{target_uin}",
            shared_rules,
            input_block,
            f"### [{key.upper()}_TASK]\n{task_prompt}",
        ]))
        res = call_ai(cfg, full_p, system_main, rate_limiter, stop_event)
        # 保存到 LOG
        with open(os.path.join(log_dir, f"03_layer_{key}.md"), "w", encoding="utf-8") as f: f.write(res)
        return key, res

    if "progress" in cb: cb["progress"](70, "正在同步提取 5 层灵魂维度...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.get("reduce_workers", 5)) as executor:
        futures = {executor.submit(run_task, k, tp): k for k, tp in reduce_tasks.items()}
        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set(): break
            k, res = future.result()
            reduce_results[k] = res
            
    if "progress" in cb: cb["progress"](85, "灵魂维度初步构建完成")
    
    combined_report = "\n\n".join([
        f"# {target_uin} 人物技能中间报告",
        "## objective.md",
        reduce_results.get("objective", ""),
        "## inference.md",
        reduce_results.get("inference", ""),
        "## behavior.md",
        reduce_results.get("behavior", ""),
        "## memory.md",
        reduce_results.get("memory", ""),
        "## style.md",
        reduce_results.get("style", ""),
    ])
    with open(os.path.join(log_dir, "00_reduce_report.md"), "w", encoding="utf-8") as f:
        f.write(combined_report)
            
    return {
        "reduce_results": reduce_results,
        "combined_report": combined_report,
        "progress": 85,
        "current_stage": "Reduce"
    }
