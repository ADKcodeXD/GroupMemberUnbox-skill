import os
import concurrent.futures
from ..state import AgentState
from ..utils import read_prompt, call_ai, RateLimiter

def map_node(state: AgentState) -> dict:
    """Map 提取阶段节点"""
    stop_event = state["stop_event"]
    if stop_event.is_set(): return {}
    
    cfg = state["config"]
    chunks = state["chunks"]
    target_uin = state["target_uin"]
    map_workers = cfg.get("map_workers", 5)
    
    rate_limiter = RateLimiter(
        max_calls=cfg.get("rate_limit_calls", 14),
        period=cfg.get("rate_limit_period", 60)
    )
    
    map_results = [None] * len(chunks)
    fidelity_results = [None] * len(chunks)
    
    system_map_knowledge = read_prompt("system_map.md")
    prompt_map_knowledge_tpl = read_prompt("prompt_map.md")
    system_map_fidelity = read_prompt("system_map_fidelity.md")
    prompt_map_fidelity_tpl = read_prompt("prompt_map_fidelity.md")
    
    def process_knowledge(index, chunk):
        prompt = prompt_map_knowledge_tpl.format(chunk_index=index+1, chunk=chunk, target_uin=target_uin)
        res = call_ai(cfg, prompt, system_map_knowledge, rate_limiter, stop_event)
        return "knowledge", index, res

    def process_fidelity(index, chunk):
        prompt = prompt_map_fidelity_tpl.format(chunk_index=index+1, chunk=chunk, target_uin=target_uin)
        res = call_ai(cfg, prompt, system_map_fidelity, rate_limiter, stop_event)
        return "fidelity", index, res
        
    completed = 0
    total_tasks = len(chunks) * 2
    cb = state.get("callbacks", {})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=map_workers * 2) as executor:
        futures = []
        for i in range(len(chunks)):
            futures.append(executor.submit(process_knowledge, i, chunks[i]))
            futures.append(executor.submit(process_fidelity, i, chunks[i]))
        
        for future in concurrent.futures.as_completed(futures):
            if stop_event.is_set(): break
            try:
                task_type, idx, res = future.result()
                if task_type == "knowledge":
                    map_results[idx] = res
                    log_path = os.path.join(state["session_log_dir"], f"map_chunk_{idx+1}.md")
                else:
                    fidelity_results[idx] = res
                    log_path = os.path.join(state["session_log_dir"], f"snippets_chunk_{idx+1}.md")
                    
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(res)
            except Exception as e:
                print(f"Map 任务失败: {e}")
            
            completed += 1
            if "progress" in cb:
                # 映射 15% -> 65% 的进度
                p = 15 + int((completed / total_tasks) * 50)
                cb["progress"](p, f"正在提取分片特征... ({completed}/{total_tasks})")
            
    return {
        "map_results": map_results,
        "fidelity_results": fidelity_results,
        "progress": 65,
        "current_stage": "Map"
    }
