import os
import json
import hashlib
import shutil
from datetime import datetime, timezone
from ..state import AgentState
from ..utils import (
    read_prompt,
    call_ai,
    RateLimiter,
    parse_structured_prompt_sections,
    render_prompt_template,
)

def skill_node(state: AgentState) -> dict:
    """Skill 蒸馏与自进化节点 - 高保真 6 层架构强化版"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    target_uin = state["target_uin"]
    evidence_base = state["evidence_base"]
    reduce_results = state.get("reduce_results", {})
    fidelity_results = state.get("fidelity_results", [])
    cb = state.get("callbacks", {})

    # 1. 结构化任务与目录准备
    out_dir = os.path.abspath(f"./skills/immortals/{target_uin}")
    os.makedirs(out_dir, exist_ok=True)
    skill_dir = os.path.join(out_dir, "skill")
    os.makedirs(skill_dir, exist_ok=True)
    
    # 2. 准备现有历史内容 (用于追加模式)
    existing_skill = {}
    if os.path.exists(skill_dir):
        for fn in os.listdir(skill_dir):
            if fn.endswith(".md"):
                try:
                    with open(os.path.join(skill_dir, fn), 'r', encoding='utf-8') as f:
                        existing_skill[fn] = f.read()
                except: pass

    # 3. 加载解析 Prompt 系统
    try:
        skill_prompts_raw = read_prompt("prompt_skill.md")
        prompts = parse_structured_prompt_sections(skill_prompts_raw)
    except Exception as e:
        return {"error": f"加载 prompt_skill.md 失败: {str(e)}"}

    system_main = prompts.get("SYSTEM", "")
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    high_value_highlights = ""
    for i, res in enumerate(fidelity_results):
        if res and res.strip():
            high_value_highlights += f"--- 分片 {i+1} 备选素材 ---\n{res}\n\n"
    if not high_value_highlights.strip():
        high_value_highlights = "（未从切片提取到符合标准的高价值原始记录）"

    shared_rules = "\n\n".join(filter(None, [
        "### [GLOBAL_EVIDENCE_PROTOCOL]\n" + prompts.get("GLOBAL_EVIDENCE_PROTOCOL", ""),
        "### [HIGH_RISK_INFERENCE_GUARDRAILS]\n" + prompts.get("HIGH_RISK_INFERENCE_GUARDRAILS", ""),
        "### [EVOLUTION_PRINCIPLES]\n" + prompts.get("EVOLUTION_PRINCIPLES", ""),
        "### [OUTPUT_ORDER]\n" + prompts.get("OUTPUT_ORDER", ""),
    ])).strip()
    input_block = render_prompt_template(
        prompts.get("INPUT", ""),
        target_uin=target_uin,
        evidence_base=evidence_base,
        high_value_highlights=high_value_highlights[:18000],
    )

    # 4. 特殊处理：LAYER_4_CHAT (高保真对话提取与上下文总结)
    def refine_chat_history():
        if "progress" in cb: cb["progress"](90, "正在深度炼化‘高保真互动样本’...")
        prompt_chat = prompts.get("LAYER_4_CHAT", "")
        full_p = "\n\n".join(filter(None, [
            f"目标角色：{target_uin}",
            shared_rules,
            input_block,
            f"### [LAYER_4_CHAT]\n{prompt_chat}",
        ]))
        return call_ai(cfg, full_p, system_main, rate_limiter, stop_event)

    # 5. 执行进化合并逻辑 (Append-Only)
    skill_data = {}
    # 自动合并从 ReduceNode 传来的层级
    layer_map = {
        "objective.md": "objective",
        "inference.md": "inference",
        "behavior.md":  "behavior",
        "memory.md":    "memory",
        "style.md":     "style"
    }

    for filename, result_key in layer_map.items():
        new_content = reduce_results.get(result_key, "")
        prev_content = existing_skill.get(filename, "")
        
        if prev_content and new_content:
            # 简单自进化逻辑：追加新发现
            merged = f"{prev_content}\n\n--- 自进化追加 ({datetime.now().strftime('%Y-%m-%d')}) ---\n\n{new_content}"
            skill_data[filename] = merged
        else:
            skill_data[filename] = new_content or prev_content

    # 异步生成 ChatHistory (因为涉及 AI 二次总结)
    skill_data["chathistory.md"] = refine_chat_history()

    # 6. 生成 SKILL.md (总控文件)
    def generate_main_skill():
        prompt_main = prompts.get("SKILL_MAIN", "")
        layer_context = "\n\n".join([
            f"## objective.md\n{skill_data.get('objective.md', '')[:3000]}",
            f"## inference.md\n{skill_data.get('inference.md', '')[:3000]}",
            f"## behavior.md\n{skill_data.get('behavior.md', '')[:3000]}",
            f"## chathistory.md\n{skill_data.get('chathistory.md', '')[:3000]}",
            f"## memory.md\n{skill_data.get('memory.md', '')[:3000]}",
            f"## style.md\n{skill_data.get('style.md', '')[:3000]}",
        ])
        full_p = "\n\n".join(filter(None, [
            f"目标角色：{target_uin}",
            shared_rules,
            input_block,
            "### [LAYER_SUMMARY_CONTEXT]",
            layer_context,
            f"### [SKILL_MAIN]\n{prompt_main}",
        ]))
        return call_ai(cfg, full_p, system_main, rate_limiter, stop_event)

    skill_data["SKILL.md"] = generate_main_skill()
    # 同时也生成一个进化日志 (evolution.md)
    skill_data["evolution.md"] = f"# 灵魂进化日志\n\n- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n- 目标: {target_uin}\n- 状态: 6层高保真模型构建/更新完成"

    # 7. 写入最终产物 (增加规范校验)
    for fn, content in skill_data.items():
        if content:
            # 针对 SKILL.md 的特殊规范校验
            if fn == "SKILL.md" and not content.lstrip().startswith("---"):
                yaml_header = f"---\nname: \"Immortal_{target_uin}\"\ndescription: \"High-fidelity digital soul profile for QQ:{target_uin}\"\nversion: \"{meta['version']}\"\nauthor: \"GroupMemberUnbox-skill\"\n---\n\n"
                content = yaml_header + content
                
            with open(os.path.join(skill_dir, fn), 'w', encoding='utf-8') as f: f.write(content)

    final_report = "\n\n".join([
        f"# {target_uin} 人物技能总报告",
        "## SKILL.md",
        skill_data.get("SKILL.md", ""),
        "## objective.md",
        skill_data.get("objective.md", ""),
        "## inference.md",
        skill_data.get("inference.md", ""),
        "## behavior.md",
        skill_data.get("behavior.md", ""),
        "## chathistory.md",
        skill_data.get("chathistory.md", ""),
        "## memory.md",
        skill_data.get("memory.md", ""),
        "## style.md",
        skill_data.get("style.md", ""),
        "## evolution.md",
        skill_data.get("evolution.md", ""),
    ])
    with open(os.path.join(out_dir, "00_final_report.md"), 'w', encoding='utf-8') as f:
        f.write(final_report)

    # 打包与元数据处理 (保持原逻辑)
    iteration = 1
    meta_path = os.path.join(skill_dir, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f: iteration = json.load(f).get("iteration", 0) + 1
        except: pass

    meta = {
        "version": "4.1.0",
        "iteration": iteration,
        "target_uin": target_uin,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "evolution_mode": "append-only",
        "sha256": ""
    }
    hash_sha256 = hashlib.sha256()
    for fn in sorted(skill_data.keys()): 
        if isinstance(skill_data[fn], str): hash_sha256.update(skill_data[fn].encode('utf-8'))
    meta["sha256"] = hash_sha256.hexdigest()
    
    with open(meta_path, 'w', encoding='utf-8') as f: json.dump(meta, f, indent=4, ensure_ascii=False)
    
    archive_name = os.path.join(out_dir, f"{target_uin}_v{iteration}_{datetime.now().strftime('%Y%m%d')}")
    try:
        shutil.make_archive(archive_name, 'zip', skill_dir)
        if os.path.exists(archive_name + ".skill"): os.remove(archive_name + ".skill")
        os.rename(archive_name + ".zip", archive_name + ".skill")
    except: pass

    return {
        "skill_dir": out_dir,
        "iteration": iteration,
        "combined_report": final_report,
        "progress": 100,
        "current_stage": "Completed"
    }
