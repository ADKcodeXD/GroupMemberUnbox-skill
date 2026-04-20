import concurrent.futures
import json
import os

from ..state import AgentState
from ..utils import RateLimiter, call_ai, call_ollama_chat, read_prompt
from ...retrieval.embed_index import ensure_specific_ollama_model
from ...retrieval.highlight_selector import (
    format_fidelity_candidates_markdown,
    select_chunk_candidates,
)


def map_node(state: AgentState) -> dict:
    """Map 阶段：并行提取知识证据与高保真对话片段。"""
    stop_event = state["stop_event"]
    if stop_event.is_set():
        return {}

    cfg = state["config"]
    chunks = state["chunks"]
    target_uin = state["target_uin"]
    map_workers = cfg.get("map_workers", 5)

    rate_limiter = RateLimiter(
        max_calls=cfg.get("rate_limit_calls", 14),
        period=cfg.get("rate_limit_period", 60),
    )

    map_results = [None] * len(chunks)
    fidelity_results = [None] * len(chunks)

    system_map_knowledge = read_prompt("system_map.md")
    prompt_map_knowledge_tpl = read_prompt("prompt_map.md")
    system_map_fidelity = read_prompt("system_map_fidelity.md")
    prompt_map_fidelity_tpl = read_prompt("prompt_map_fidelity.md")

    highlight_candidates = []
    candidate_path = state.get("highlight_candidates_path")
    if candidate_path and os.path.exists(candidate_path):
        try:
            with open(candidate_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        highlight_candidates.append(json.loads(line))
        except Exception:
            highlight_candidates = []

    def process_knowledge(index, chunk):
        prompt = prompt_map_knowledge_tpl.format(
            chunk_index=index + 1,
            chunk=chunk,
            target_uin=target_uin,
        )
        stream_key = f"map_chunk_{index + 1}"
        def on_chunk(delta):
            if "preview_stream" in cb:
                cb["preview_stream"](stream_key, delta)

        res = call_ai_stream(cfg, prompt, system_map_knowledge, on_chunk, rate_limiter, stop_event)
        return "knowledge", index, res

    def process_fidelity(index, chunk):
        fidelity_provider = cfg.get("fidelity_provider", "remote")
        candidate_min = cfg.get("fidelity_candidate_min", 30)
        candidate_max = cfg.get("fidelity_candidate_max", 50)
        related_candidates = select_chunk_candidates(
            highlight_candidates,
            chunk,
            min_items=candidate_min,
            max_items=candidate_max,
        )
        candidate_markdown = format_fidelity_candidates_markdown(related_candidates)
        candidate_text = (
            "\n\n【本地高价值候选池（优先围绕这些材料抽取 fidelity）】\n"
            f"本 chunk 已筛出一共 {len(related_candidates)} 条候选，请优先围绕这些候选完成提取。\n\n"
            f"{candidate_markdown}"
        )
        fallback_prompt = (
            prompt_map_fidelity_tpl.format(
                chunk_index=index + 1,
                chunk=chunk,
                target_uin=target_uin,
            )
            + candidate_text
        )

        stream_key = f"snippets_chunk_{index + 1}"
        def on_chunk(delta):
            if "preview_stream" in cb:
                cb["preview_stream"](stream_key, delta)

        if fidelity_provider == "ollama":
            try:
                model = cfg.get("fidelity_model", "qwen3:4b")
                api_base = cfg.get("fidelity_api_base", "http://localhost:11434")
                ensure_specific_ollama_model(
                    api_base=api_base,
                    model_name=model,
                    timeout=cfg.get("fidelity_timeout", 180),
                    auto_pull=cfg.get("auto_pull_fidelity_models", True),
                )
                local_prompt = (
                    f"你正在处理第 {index + 1} 个 chunk 的高价值对话抽取任务。\n"
                    "3. 每条都必须包含：目标人物对话、上下文摘要；必要时补一小段关键上下文原话。\n"
                    "4. 目标人物对话尽量保持原句，不要改写口吻。\n"
                    "5. 候选池足够时，不要额外泛化总结，不要把整段 chunk 机械复述。\n\n"
                    "输出格式：\n"
                    "#### 1. 【语言特征提取】\n"
                    "- 口头禅与高频表达: [...]\n"
                    "- 特殊句式与标点习惯: [...]\n\n"
                    "#### 2. 【高价值目标人物对话列表】\n"
                    "- F1 | [时间] | [场景]\n"
                    "  目标人物对话: ...\n"
                    "  上下文摘要: ...\n"
                    "  关键上下文原话: ...\n\n"
                    "- F2 ........"
                    f"【候选材料开始】\n{candidate_markdown}\n【候选材料结束】\n\n"
                    f"【原始 chunk（仅供补充参考）开始】\n{chunk}\n【原始 chunk 结束】"
                )
                res = call_ollama_chat_stream(
                    api_base=api_base,
                    model=model,
                    prompt_text=local_prompt,
                    system_prompt=system_map_fidelity,
                    on_chunk=on_chunk,
                    timeout=cfg.get("fidelity_timeout", 180),
                    temperature=cfg.get("fidelity_temperature", 0.2),
                )
            except Exception:
                res = call_ai_stream(
                    cfg,
                    fallback_prompt,
                    system_map_fidelity,
                    on_chunk,
                    rate_limiter,
                    stop_event,
                )
        else:
            res = call_ai_stream(
                cfg,
                fallback_prompt,
                system_map_fidelity,
                rate_limiter,
                stop_event,
            )
        return "fidelity", index, res

    completed = 0
    total_tasks = len(chunks) * 2
    cb = state.get("callbacks", {})

    with concurrent.futures.ThreadPoolExecutor(max_workers=map_workers * 2) as executor:
        futures = []
        for i, chunk in enumerate(chunks):
            futures.append(executor.submit(process_knowledge, i, chunk))
            futures.append(executor.submit(process_fidelity, i, chunk))

        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set():
                break
            try:
                task_type, idx, res = future.result()
                if task_type == "knowledge":
                    map_results[idx] = res
                    log_path = os.path.join(state["session_log_dir"], f"map_chunk_{idx + 1}.md")
                else:
                    fidelity_results[idx] = res
                    log_path = os.path.join(state["session_log_dir"], f"snippets_chunk_{idx + 1}.md")

                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(res)
            except Exception as e:
                print(f"Map 任务失败: {e}")

            completed += 1
            if "progress" in cb:
                progress = 15 + int((completed / total_tasks) * 50)
                cb["progress"](progress, f"正在提取分片特征... ({completed}/{total_tasks})")

    return {
        "map_results": map_results,
        "fidelity_results": fidelity_results,
        "progress": 65,
        "current_stage": "Map",
    }
