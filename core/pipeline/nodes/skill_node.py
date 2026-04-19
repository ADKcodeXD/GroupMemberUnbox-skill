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
    final_report = state["combined_report"]
    
    # 汇总风味记录
    high_value_highlights = ""
    for res in state["fidelity_results"]:
        if res: high_value_highlights += res + "\n\n"

    out_dir = os.path.abspath(f"./skills/immortals/{target_uin}")
    os.makedirs(out_dir, exist_ok=True)
    skill_dir = os.path.join(out_dir, "skill")
    os.makedirs(skill_dir, exist_ok=True)
    
    # 保存过程文件
    with open(os.path.join(out_dir, "01_raw_chat_context.txt"), 'w', encoding='utf-8') as f: f.write(chat_text)
    with open(os.path.join(out_dir, "02_evidence_base.md"), 'w', encoding='utf-8') as f: f.write(evidence_base)
    with open(os.path.join(out_dir, "03_final_profile_report.md"), 'w', encoding='utf-8') as f: f.write(final_report)
    
    skill_files_prompts = {
        "procedure.md": """分析目标人物在处理事务、面对冲突或日常操作时的【行为逻辑 (Procedure)】。
重点提取：
1. 决策风格：是果断、犹豫还是基于特定逻辑？
2. 任务处理：面对多任务、紧急情况时的反应模式。
3. 习惯动作：在文字交流中体现出的固定行为特征。
4. 资源偏好：在解决问题时习惯依赖什么（技术、直觉还是他人）？
要求：基于证据库给出具体的行为模式总结。""",

        "interaction.md": """分析目标人物的【交互风格 (Interaction)】与话语体系。
重点提取：
1. 语气语调：是冷酷、热情、幽默还是带有攻击性？
2. 标志性词汇：提取其高频使用的、具有个人特色的词汇或口癖。
3. 社交边界：与人交流时的距离感、尊重程度或随意度。
4. 冲突表现：在吵架、被质疑或尴尬时刻的语言反击模式。
要求：给出其“魂”层面的文字交互特征。""",

        "memory.md": """提取目标人物的【核心记忆与背景上下文 (Memory)】。
重点提取：
1. 重大事件：其提到的转折点、成就或创伤。
2. 社会关系：核心人际关系网及其对其的影响。
3. 长期偏好：长期坚持的爱好、信仰或价值观来源。
4. 环境背景：其成长、工作或生活的环境对其性格的塑造证据。
要求：构建其作为“人”的连续性背景。""",

        "personality.md": """界定目标人物的【人格特质 (Personality)】。
重点提取：
1. MBTI/人格分类倾向：根据言行推测其人格类型并提供证据。
2. 核心驱动力：他最渴望什么？（如：认同感、绝对理性、混乱、安全感）。
3. 情感阈值：什么能让他兴奋、愤怒或悲伤？
4. 道德底线：他在言语中表现出的价值判断标准。
要求：深入其心理底层逻辑。""",

        "conflicts.md": """识别目标人物的【潜在矛盾与未竟之事 (Conflicts)】。
重点提取：
1. 内在矛盾：言行不一之处、自我纠结的焦点。
2. 外部敌对：与其产生过严重冲突的对象或观念。
3. 情感空缺：他在潜意识中表现出的缺失感。
4. 待办项：他提到过想做但未做的事情。
要求：揭示其性格中的“不完美”与动态。""",

        "SKILL.md": f"""按照 immortal-skill 规范，生成该人物的【总控 SKILL.md】。
要求包含：
- YAML Frontmatter: name 为 {target_uin}
- 核心愿景：概括该数字生命的本质。
- 指令引导：教导外部模型如何完美模拟此人。
- 模块引用：关联上述生成的五个子模块。"""
    }
    
    rate_limiter = RateLimiter(cfg.get("rate_limit_calls", 14), 60)
    def generate_skill_file(filename, specific_instruction):
        system_skill = "你是一位精通 immortal-skill 框架的数字永生架构师。"
        chat_sample = chat_text if len(chat_text) < 200000 else chat_text[-200000:]
        prompt_skill = f"目标：{target_uin}\n对话：{chat_sample}\n证据：{evidence_base}\n任务：{specific_instruction}"
        return filename, call_ai(cfg, prompt_skill, system_skill, rate_limiter, stop_event)

    skill_data = {}
    total_skills = len(skill_files_prompts)
    completed_skills = 0
    cb = state.get("callbacks", {})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.get("skill_workers", 6)) as executor:
        futures = [executor.submit(generate_skill_file, fn, ins) for fn, ins in skill_files_prompts.items()]
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
        
    # 5. 生成元数据与打包 (完整逻辑)
    timestamp = datetime.now(timezone.utc).isoformat()
    meta = {
        "version": "3.0.0",
        "target_uin": target_uin,
        "created_at": timestamp,
        "sha256": ""
    }
    
    # 5.1 计算文件夹内容哈希 (确保 Skill 完整性)
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
        
    # 5.2 打包为 zip 并重命名为 .skill
    archive_name = os.path.join(out_dir, f"{target_uin}_skill_{datetime.now().strftime('%Y%m%d')}")
    try:
        # 如果已存在则先删除
        if os.path.exists(archive_name + ".zip"): os.remove(archive_name + ".zip")
        if os.path.exists(archive_name + ".skill"): os.remove(archive_name + ".skill")
        
        import shutil
        shutil.make_archive(archive_name, 'zip', skill_dir)
        os.rename(archive_name + ".zip", archive_name + ".skill")
    except Exception as e:
        print(f"打包失败: {e}")
    
    return {
        "skill_dir": out_dir,
        "progress": 100,
        "current_stage": "Completed"
    }
