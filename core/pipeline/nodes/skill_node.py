import os
import json
import hashlib
import shutil
import concurrent.futures
from datetime import datetime, timezone
from ..state import AgentState
from ..utils import read_prompt, call_ai, RateLimiter

def skill_node(state: AgentState) -> dict:
    """Skill 蒸馏阶段节点"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    target_uin = state["target_uin"]
    chat_text = state["chat_text"]
    evidence_base = state["evidence_base"]
    reduce_results = state.get("reduce_results", {})
    
    # 汇总风味记录
    high_value_highlights = ""
    for res in state["fidelity_results"]:
        if res: high_value_highlights += res + "\n\n"

    out_dir = os.path.abspath(f"./skills/immortals/{target_uin}")
    os.makedirs(out_dir, exist_ok=True)
    skill_dir = os.path.join(out_dir, "skill")
    os.makedirs(skill_dir, exist_ok=True)
    
    # 保存过程文件 (分模块输出，不再挤在一个大文件里)
    with open(os.path.join(out_dir, "01_raw_chat_context.txt"), 'w', encoding='utf-8') as f: f.write(chat_text)
    with open(os.path.join(out_dir, "02_evidence_base.md"), 'w', encoding='utf-8') as f: f.write(evidence_base)
    with open(os.path.join(out_dir, "03_resume.md"), 'w', encoding='utf-8') as f: f.write(reduce_results.get("resume", ""))
    with open(os.path.join(out_dir, "04_analysis.md"), 'w', encoding='utf-8') as f: f.write(reduce_results.get("analysis", ""))
    with open(os.path.join(out_dir, "05_literary.md"), 'w', encoding='utf-8') as f: f.write(reduce_results.get("literary", ""))
    with open(os.path.join(out_dir, "06_profiling.md"), 'w', encoding='utf-8') as f: f.write(reduce_results.get("profiling", ""))
    with open(os.path.join(out_dir, "07_style.md"), 'w', encoding='utf-8') as f: f.write(reduce_results.get("style", ""))
    
    # 定义蒸馏任务及其所需的特定上下文模块
    skill_tasks = {
        "resume.md": {
            "prompt": """生成目标人物的【个人简历/背景档案 (Resume)】。
要求：基于提供的人物简历模块，整理成一份清晰、客观的个人档案。包含教育经历、职场履历、技能特长及健康/生存现状。
!! 注意：此文件用于定义模型的“基础事实认知”，必须严谨且详实。""",
            "context": reduce_results.get("resume", "")
        },
        "style.md": {
            "prompt": """生成目标人物的【说话风格指南 (Speaking Style Guide)】。
要求：基于汇总的语言特征、高频词汇统计以及对话原话，提炼出其核心交流模式。
需包含：
1. 口头禅与特定语气词。
2. 句式习惯（如长短句、标点偏好）。
3. 模拟指令（3条具体的 System Prompt 指令）。""",
            "context": reduce_results.get("style", "")
        },
        "chathistory.md": {
            "prompt": """生成一份密集的【历史对话片段集 (Chat History)】用以语料训练。
要求：从高价值对话片段中，精选 20-30 条最能体现人物“嘴脸”和“口癖”的原始对话。
!! 注意：不要添加任何 AI 的总结或解释，直接以原始对话流的形式呈现，哪怕是带攻击性或负面情绪的。这将作为模型浸入式学习的第一手资料。""",
            "context": high_value_highlights
        },
        "procedure.md": {
            "prompt": """分析目标人物在处理事务或冲突时的【行为逻辑 (Procedure)】。
要求：模拟其真实的决策过程。例如：面对 Bug 时他是甩锅还是解决？面对压力时是逃避还是对冲？
!! 关键提醒：你是在模拟一个有限的、真实的、甚至有缺陷的人，而非一个全知全能的助手。""",
            "context": reduce_results.get("analysis", "")
        },
        "interaction.md": {
            "prompt": """定义人物的【文字交互模式 (Interaction)】。
要求：明确其语速节奏、长短句切换逻辑、高频黑话及社交防御姿态。
!! 关键提醒：你是为了“模拟本人”，而非“解决问题”。如果一个问题在现实中这人不知道，或者这人不想理，模拟时也应体现这种“拒绝”或“无知”。""",
            "context": high_value_highlights + "\n" + reduce_results.get("profiling", "")
        },
        "personality.md": {
            "prompt": """界定人物的【人格底层逻辑 (Personality)】。
要求：深挖其核心防御机制（如犬儒主义、赌徒心态）。提供 5 条体现其性格底色的原始金句。
!! 关键提醒：强调其性格的“硬度”与独特性，避免生成模棱两可、温柔客气的标准 AI 人格。""",
            "context": reduce_results.get("analysis", "") + "\n" + reduce_results.get("literary", "")
        },
        "memory.md": {
            "prompt": """构建人物的【核心记忆与世界观 (Memory)】。
要求：基于其背景和叙事，总结出对其人生观产生重大影响的事件。
!! 关键提醒：他的世界观通常是偏颇的、基于个人经历的，模拟时必须保持这种视角的局限性。""",
            "context": reduce_results.get("literary", "") + "\n" + reduce_results.get("resume", "")
        },
        "conflicts.md": {
            "prompt": """识别其内在的【矛盾与张力 (Conflicts)】。
要求：揭示其言行不一之处、未实现的幻想及核心恐惧。""",
            "context": reduce_results.get("analysis", "")
        },
        "SKILL.md": {
            "prompt": f"""按照 immortal-skill 规范，生成【总控 SKILL.md】总控文件。
!! 要求：你必须在报告中【完全引用】并【列举】以下所有 8 个子模块，并说明它们的约束效力。

### 0. YAML Frontmatter (必须位于文件最开头)
name: [AI生成：仅限小写英文字母名，如: yuxian-skill]
alias: [AI生成：绰号/标题，可包含中文]
description: "[AI生成：一句话本质定义]"
---

### 1. 人格定义与核心原则
[定义目标人物的核心特质，明确其非全知、有情绪偏见、非助手的真实人类特质]

### 2. 子模块引用清单 (必选，不得遗漏)
下游模型需严格遵循以下子模块的约束：
- **[style.md] 语言风格与节律**：定义句式习惯、高频口癖（核心约束）。
- **[resume.md] 个人背景档案**：事实基座，决定其“知道什么”和“不知道什么”。
- **[chathistory.md] 原始对话片段**：1:1 还原真实互动的“体感”。
- **[interaction.md] 文字交互逻辑**：定义语速、节奏及社交防御姿态。
- **[personality.md] 人格底层逻辑**：定义核心动力与性格硬度。
- **[procedure.md] 决策处理逻辑**：定义面对变数时的典型反应。
- **[memory.md] 核心记忆锚点**：定义世界观的边界与敏感点。
- **[conflicts.md] 内在矛盾张力**：揭示言行违和处与防御机制。

### 3. 模拟运行指南
[说明如何结合上述模块，让 AI 真正“活”过来，而不是机械地回答问题]
""",
            "context": evidence_base # SKILL.md 需要全局视野
        }
    }
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    
    def generate_skill_file(filename, task_cfg):
        system_skill = "你是一位精通 immortal-skill 框架的数字永生架构师，致力于 1:1 还原人类灵魂的真实质感与局限性。"
        prompt_skill = (
            f"目标：{target_uin}\n"
            f"特定参考上下文：\n{task_cfg['context']}\n\n"
            f"高价值对话参考：\n{high_value_highlights[:5000]}\n\n" # 保持部分风味
            f"任务指令：\n{task_cfg['prompt']}"
        )
        return filename, call_ai(cfg, prompt_skill, system_skill, rate_limiter, stop_event)

    skill_data = {}
    total_skills = len(skill_tasks)
    completed_skills = 0
    cb = state.get("callbacks", {})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.get("skill_workers", 6)) as executor:
        futures = [executor.submit(generate_skill_file, fn, t) for fn, t in skill_tasks.items()]
        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set(): break
            fn, content = future.result()
            skill_data[fn] = content
            completed_skills += 1
            if "progress" in cb:
                p = 90 + int((completed_skills / total_skills) * 10)
                cb["progress"](p, f"正在构筑数字生命灵魂... ({completed_skills}/{total_skills})")

    for fn, content in skill_data.items():
        with open(os.path.join(skill_dir, fn), 'w', encoding='utf-8') as f: f.write(content)
        
    # 5. 生成元数据与打包
    timestamp = datetime.now(timezone.utc).isoformat()
    meta = {
        "version": "3.1.0",
        "target_uin": target_uin,
        "created_at": timestamp,
        "sha256": ""
    }
    
    hash_sha256 = hashlib.sha256()
    for root, dirs, files in os.walk(skill_dir):
        for file in sorted(files):
            if file == "metadata.json": continue
            with open(os.path.join(root, file), 'rb') as f:
                while chunk := f.read(8192):
                    hash_sha256.update(chunk)
    
    meta["sha256"] = hash_sha256.hexdigest()
    with open(os.path.join(skill_dir, "metadata.json"), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)
        
    archive_name = os.path.join(out_dir, f"{target_uin}_skill_{datetime.now().strftime('%Y%m%d')}")
    try:
        if os.path.exists(archive_name + ".zip"): os.remove(archive_name + ".zip")
        if os.path.exists(archive_name + ".skill"): os.remove(archive_name + ".skill")
        shutil.make_archive(archive_name, 'zip', skill_dir)
        os.rename(archive_name + ".zip", archive_name + ".skill")
    except Exception as e:
        print(f"打包失败: {e}")
    
    return {
        "skill_dir": out_dir,
        "progress": 100,
        "current_stage": "Completed"
    }
