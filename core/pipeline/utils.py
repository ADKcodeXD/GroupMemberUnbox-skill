import os
import requests
import time
import threading
from typing import Dict, Any
from PyQt5.QtCore import QThread, pyqtSignal

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "prompts")

def read_prompt(filename):
    """从 prompts/ 目录读取 prompt 模板"""
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

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
    """通用的 AI 调用函数，支持实时停止信号"""
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
        "max_tokens": config.get("max_tokens", 8192)
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
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            resp_json = response.json()
            res = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            return res if res is not None else ""
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return f"【AI请求失败: {str(e)}】"

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
    """在启动分析前估算分段数量和预计时间 (完整还原原始逻辑)"""
    chunk_size = config.get("chunk_size", 100000)
    num_chunks = max(1, (chat_text_len + chunk_size - 1) // chunk_size)
    map_workers = config.get("map_workers", 5)
    rate_limit = config.get("rate_limit_calls", 14)
    
    # Map 阶段: 每 chunk 2次 API 调用
    num_map_calls = num_chunks * 2
    calls_per_minute = min(map_workers * 2, rate_limit)
    map_time_min = num_map_calls / calls_per_minute
    
    # 汇总/Reduce/Skill 预估时间
    total_min = map_time_min + 1.0 + 1.5 + 2.0
    total_api_calls = num_map_calls + 1 + 4 + 6 

    # 费用估算 (Token 估算逻辑)
    est_map_in = num_chunks * (5000 + 2 * chunk_size)
    est_map_out = num_chunks * 6000
    est_merge_in = 2000 + (num_chunks * 2000)
    est_merge_out = 8000
    est_reduce_in = 4 * (2000 + est_merge_out + (num_chunks * 4000))
    est_reduce_out = 4 * 4000
    est_skill_in = 6 * (12000 + est_merge_out + 4000)
    est_skill_out = 6 * 3000
    
    total_in_tokens = est_map_in + est_merge_in + est_reduce_in + est_skill_in
    total_out_tokens = est_map_out + est_merge_out + est_reduce_out + est_skill_out
    
    price_in = config.get("price_per_m_input", 0.95)
    price_out = config.get("price_per_m_output", 3.15)
    total_cost = (total_in_tokens / 1_000_000 * price_in) + (total_out_tokens / 1_000_000 * price_out)
    
    return {
        "num_chunks": num_chunks,
        "total_api_calls": total_api_calls,
        "estimated_minutes": round(total_min, 1),
        "total_in_tokens": round(total_in_tokens / 1000, 1),  # K tokens
        "total_out_tokens": round(total_out_tokens / 1000, 1), # K tokens
        "estimated_cost": round(total_cost, 2)
    }
