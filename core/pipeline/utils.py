import os
import requests
import time
import threading
from typing import Dict, Any

# PyQt5 is optional — only needed for GUI mode (TestApiThread)
try:
    from PyQt5.QtCore import QThread, pyqtSignal
    _HAS_PYQT5 = True
except ImportError:
    _HAS_PYQT5 = False

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "prompts")

def read_prompt(filename):
    """从 prompts/ 目录读取 prompt 模板"""
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def parse_structured_prompt_sections(raw_text: str) -> Dict[str, str]:
    """解析 `### [SECTION]` 结构化 prompt 文件。"""
    sections: Dict[str, str] = {}
    current_key = None
    current_lines = []

    for line in raw_text.splitlines():
        if line.startswith("### [") and line.endswith("]"):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[5:-1]
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def render_prompt_template(template: str, **kwargs: Any) -> str:
    """安全渲染 prompt 模板中的简单占位符。"""
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered

class RateLimiter:
    """线程安全的令牌桶/速率限制器"""
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(now)

def call_ai(config: Dict[str, Any], prompt_text: str, system_prompt: str, rate_limiter: RateLimiter, stop_event: threading.Event) -> str:
    """通用的 AI 调用函数，同步获取完整结果。"""
    return call_ai_stream(config, prompt_text, system_prompt, None, rate_limiter, stop_event)


def call_ai_stream(config: Dict[str, Any], prompt_text: str, system_prompt: str, on_chunk, rate_limiter: RateLimiter, stop_event: threading.Event) -> str:
    """支持流式输出的 AI 调用函数。如果 on_chunk 为空则退化为非流式。"""
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ],
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 8192),
        "stream": on_chunk is not None
    }
    
    api_url = config["api_base"].rstrip('/')
    if not api_url.endswith("/chat/completions"):
        api_url = f"{api_url}/chat/completions"
        
    max_retries = config.get("max_retries", 3)
    timeout = config.get("request_timeout", 300)
    
    for attempt in range(max_retries):
        if stop_event.is_set():
            return "【任务已终止】"
        if rate_limiter:
            rate_limiter.wait()
            
        try:
            full_content = []
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout, stream=payload["stream"])
            response.raise_for_status()
            
            if not payload["stream"]:
                res = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                return res or ""
            
            import json
            for line in response.iter_lines():
                if stop_event.is_set(): break
                if not line: continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]": break
                    try:
                        chunk_json = json.loads(data_str)
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            full_content.append(delta)
                            if on_chunk: on_chunk(delta)
                    except:
                        continue
            return "".join(full_content)
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return f"【AI请求失败: {str(e)}】"


def call_ollama_chat(
    api_base: str,
    model: str,
    prompt_text: str,
    system_prompt: str = "",
    timeout: int = 300,
    temperature: float = 0.2,
) -> str:
    """调用 Ollama chat 接口。同步版本包装。"""
    return call_ollama_chat_stream(api_base, model, prompt_text, system_prompt, None, timeout, temperature)


def call_ollama_chat_stream(
    api_base: str,
    model: str,
    prompt_text: str,
    system_prompt: str = "",
    on_chunk=None,
    timeout: int = 300,
    temperature: float = 0.2,
) -> str:
    """调用 Ollama chat 接口，支持流式输出。"""
    api_base = (api_base or "http://localhost:11434").rstrip("/")
    url = f"{api_base}/api/chat"
    payload = {
        "model": model,
        "stream": on_chunk is not None,
        "messages": [],
        "options": {"temperature": temperature},
    }
    if system_prompt:
        payload["messages"].append({"role": "system", "content": system_prompt})
    payload["messages"].append({"role": "user", "content": prompt_text})
    
    try:
        response = requests.post(url, json=payload, timeout=timeout, stream=payload["stream"])
        response.raise_for_status()
        
        full_content = []
        if not payload["stream"]:
            return response.json().get("message", {}).get("content", "") or ""
            
        import json
        for line in response.iter_lines():
            if not line: continue
            chunk = json.loads(line.decode("utf-8"))
            content = chunk.get("message", {}).get("content", "")
            if content:
                full_content.append(content)
                if on_chunk: on_chunk(content)
            if chunk.get("done"): break
        return "".join(full_content)
    except Exception as e:
        return f"【Ollama 请求失败: {str(e)}】"

# TestApiThread 仅在有 PyQt5 时定义（GUI 专用）
if _HAS_PYQT5:
    class TestApiThread(QThread):
        """专门用于测试 API 连通性的线程"""
        finished = pyqtSignal(bool, str)
        
        def __init__(self, config):
            super().__init__()
            self.config = config
            
        def run(self):
            cfg = self.config
            headers = {
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello!"}
                ],
                "max_tokens": 100
            }
            
            api_url = cfg["api_base"].rstrip('/')
            if not api_url.endswith("/chat/completions"):
                api_url = f"{api_url}/chat/completions"
                
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=20)
                response.raise_for_status()
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "Success")
                self.finished.emit(True, content)
            except Exception as e:
                self.finished.emit(False, str(e))

def estimate_analysis(chat_text_len, config):
    """在启动分析前估算远程调用成本与本地检索开销。"""
    chunk_size = config.get("chunk_size", 100000)
    num_chunks = max(1, (chat_text_len + chunk_size - 1) // chunk_size)
    map_workers = config.get("map_workers", 5)
    rate_limit = config.get("rate_limit_calls", 14)

    # 远程调用拆分
    map_knowledge_calls = num_chunks
    fidelity_provider = config.get("fidelity_provider", "remote")
    map_fidelity_calls = num_chunks if fidelity_provider == "remote" else 0
    merge_calls = 1
    reduce_calls = 5   # objective / inference / behavior / memory / style
    skill_calls = 2    # chathistory + SKILL.md
    base_remote_calls = map_knowledge_calls + map_fidelity_calls + merge_calls + reduce_calls + skill_calls

    # Agent 模式附加远程调用估算
    agent_mode = config.get("agent_mode", False)
    audit_remote_calls = 0
    if agent_mode:
        # retrieve 已语义本地化，远程主要仍来自 audit/refine 循环
        # 这里给一个保守范围中值
        audit_remote_calls = 4

    total_remote_calls = base_remote_calls + audit_remote_calls

    # 本地 embedding / 语义检索开销
    embedding_enabled = config.get("embedding_enabled", False)
    embedding_requests = 1 if embedding_enabled else 0
    semantic_retrieval_enabled = config.get("semantic_retrieval_enabled", True)

    # 时间估算：远程为主，本地索引额外给一个小常数
    calls_per_minute = max(1, min(map_workers * 2, rate_limit))
    remote_time_min = total_remote_calls / calls_per_minute
    local_time_min = 0.0
    if embedding_enabled:
        # 粗略估算：消息 embedding、候选池生成、语义检索初始化
        local_time_min += 0.3
    if fidelity_provider == "ollama":
        local_time_min += max(0.3, num_chunks * 0.08)
    total_min = remote_time_min + local_time_min + 0.8

    # 费用估算：仅估算远程 LLM 成本；本地 embedding 不计入美元成本
    est_map_in = num_chunks * (5000 + 2 * chunk_size)
    est_map_out = num_chunks * 6000
    est_merge_in = 2000 + (num_chunks * 2000)
    est_merge_out = 8000
    est_reduce_in = 5 * (2500 + est_merge_out + (num_chunks * 3500))
    est_reduce_out = 5 * 3500
    est_skill_in = 2 * (14000 + est_merge_out + 5000)
    est_skill_out = 2 * 4500
    est_audit_in = 0
    est_audit_out = 0
    if agent_mode:
        est_audit_in = 4 * (6000 + est_merge_out)
        est_audit_out = 4 * 2500

    total_in_tokens = est_map_in + est_merge_in + est_reduce_in + est_skill_in
    total_in_tokens += est_audit_in
    total_out_tokens = est_map_out + est_merge_out + est_reduce_out + est_skill_out + est_audit_out

    price_in = config.get("price_per_m_input", 0.95)
    price_out = config.get("price_per_m_output", 3.15)
    total_cost = (total_in_tokens / 1_000_000 * price_in) + (total_out_tokens / 1_000_000 * price_out)

    return {
        "num_chunks": num_chunks,
        "total_api_calls": total_remote_calls,
        "remote_api_calls": total_remote_calls,
        "base_remote_calls": base_remote_calls,
        "audit_remote_calls": audit_remote_calls,
        "embedding_enabled": embedding_enabled,
        "embedding_requests": embedding_requests,
        "fidelity_provider": fidelity_provider,
        "semantic_retrieval_enabled": semantic_retrieval_enabled,
        "estimated_minutes": round(total_min, 1),
        "remote_minutes": round(remote_time_min, 1),
        "local_minutes": round(local_time_min, 1),
        "total_in_tokens": round(total_in_tokens / 1000, 1),
        "total_out_tokens": round(total_out_tokens / 1000, 1),
        "estimated_cost": round(total_cost, 2),
        "cost_scope": "仅远程 LLM 成本；未包含本地 embedding / CPU / GPU / 电费",
    }
