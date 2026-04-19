"""
全局配置管理模块。
所有可调节参数集中管理，支持 JSON 持久化。
"""
import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

# API 镜像站预设
API_PRESETS = {
    "本地 (AIStudioToAPI)": "http://localhost:7860/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "SiliconFlow": "https://api.siliconflow.cn/v1",
    "Moonshot (Kimi)": "https://api.moonshot.cn/v1",
    "自定义": "",
}

DEFAULT_CONFIG = {
    # ===== 数据处理 =====
    "context_window": 2,           # 上下文截取条数（上下各N条）
    "chunk_size": 100000,          # 每个分段的最大字符数
    "sample_limit": 5000,          # 抽样目标条数
    "sample_enabled": True,        # 是否启用抽样
    "only_target": False,          # 仅提取目标人发言

    # ===== 并发控制 =====
    "map_workers": 5,              # Map 阶段并发数
    "reduce_workers": 4,           # Reduce 阶段并发数
    "skill_workers": 6,            # Skill 蒸馏并发数
    "rate_limit_calls": 14,        # 每分钟最大 API 调用次数
    "rate_limit_period": 60,       # 限流周期（秒）

    # ===== API 设置 =====
    "api_key": "",
    "api_base": "http://localhost:7860/v1",
    "api_preset": "本地 (AIStudioToAPI)",
    "model": "gemini-3-flash-preview",
    "temperature": 0.2,
    "max_tokens": 8192,
    "request_timeout": 300,        # API 超时秒数
    "max_retries": 3,              # 最大重试次数

    # ===== Agent 模式 =====
    "agent_mode": False,           # 是否开启 Agent 深度审计模式

    # ===== 费用估算 (默认按 Gemini 1.5 Flash 类似档位) =====
    "price_per_m_input": 0.95,     # $ / M input tokens
    "price_per_m_output": 3.15,    # $ / M output tokens
}


def load_config() -> dict:
    """加载配置，如果文件不存在则使用默认值"""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            config.update(saved)
        except Exception as e:
            print(f"[Config] 加载配置失败，使用默认值: {e}")
    return config


def save_config(config: dict):
    """保存配置到 JSON 文件"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Config] 保存配置失败: {e}")
