---
name: group-member-unbox
description: >
  Analyze QQ group chat JSON exports to extract a target person's personality profile,
  behavioral patterns, and speaking style, then distill the results into an installable
  skill pack ("immortal-skill"). Use when the user has QQ chat history JSON files
  (exported via qq-chat-exporter) and wants to profile a specific group member by QQ number.
license: MIT
metadata:
  author: shuakami
  version: "2.0"
  compatibility: Requires Python 3.10+, requests, jieba, langgraph, typing-extensions. PyQt5 only needed for GUI mode.
---

# Group Member Unbox (群友炼化机)

从 QQ 聊天记录 JSON 中提取目标人物的全维度画像，并蒸馏为可安装的 Agent Skill 包。

## When to use this skill

- 用户提供了 QQ 聊天记录的 JSON 导出文件（来自 [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter)）
- 用户想分析某个群成员的性格、行为模式、说话风格
- 用户想生成一个可用于 AI 角色扮演的 "数字灵魂" skill 包

## Prerequisites

安装依赖（不需要 PyQt5，CLI 模式无 GUI 依赖）：

```bash
pip install requests jieba langgraph typing-extensions
```

用户必须提供一个 OpenAI 兼容的 API Key（支持 OpenRouter / DeepSeek / SiliconFlow / Moonshot / 本地部署）。

## Available scripts

- **`scripts/run_pipeline.py`** — 完整分析 Pipeline 的 CLI 入口，支持预估、导出、断点续传

## Workflow

### Step 1: 预估资源消耗

在运行分析前，先预估 API 调用量和费用：

```bash
python scripts/run_pipeline.py \
    --files <chat1.json> [chat2.json ...] \
    --target-uin <QQ号> \
    --estimate
```

输出 JSON 格式的预估信息（分段数、API 调用次数、Token 量、预计费用）。

### Step 2: 运行完整分析

```bash
python scripts/run_pipeline.py \
    --files <chat1.json> [chat2.json ...] \
    --target-uin <QQ号> \
    --api-key <your-api-key> \
    --api-base <api-base-url> \
    --model <model-name>
```

Pipeline 自动执行 6 个阶段：Extract → Map → Merge → (可选 Audit) → Reduce → Skill。

### Step 3: 查看产物

分析完成后，输出 JSON 包含 `skill_dir` 路径。产物结构：

```
skills/immortals/<QQ号>/
├── skill/
│   ├── SKILL.md          # 目标人物的 skill 总控文件
│   ├── resume.md          # 人物简历
│   ├── style.md           # 说话风格指南
│   ├── chathistory.md     # 高浓度原话语料
│   ├── interaction.md     # 社交模式
│   ├── personality.md     # 性格内核
│   ├── procedure.md       # 行为逻辑
│   ├── memory.md          # 记忆与经历
│   ├── conflicts.md       # 矛盾与阴暗面
│   └── metadata.json      # 元数据
├── 01_raw_chat_context.txt
├── 02_evidence_base.md
└── 03-07_*.md             # 各维度中间报告
```

## Common options

| 参数 | 说明 |
|------|------|
| `--agent-mode` | 开启 Agent 深度审计（RAG 检索 + 多轮验证，耗时增 2-3 倍） |
| `--no-sample` | 禁用智能抽样（适用于小数据量 < 5000 条） |
| `--only-target` | 仅提取目标人发言（去除上下文，减少 Token 消耗） |
| `--export-txt FILE` | 仅导出脱水文本，不运行 AI 分析 |
| `--resume LOG_DIR` | 从指定会话目录断点续传 |
| `--config FILE` | 使用自定义配置文件（参考 `config.json.example`） |
| `--quiet` | 静默模式，仅输出最终 JSON 结果 |

## Gotchas

- JSON 文件必须是 [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter) 的导出格式，包含 `messages` 数组和 `chatInfo` 对象。
- `--target-uin` 是 QQ 号（纯数字），不是昵称。可以在 JSON 文件的 `messages[].sender.uin` 中查找。
- API 调用量与聊天记录长度成正比。10 万条消息可能需要 30+ 次 API 调用，花费 $0.5-2。
- 使用 `--agent-mode` 会启用 RAG 审计循环（最多 3 轮审计 + 5 次检索），显著提升准确度但耗时增加。
- 中途中断可通过 `--resume logs/<session_dir>` 续传，Pipeline 会跳过已完成的阶段。
- `config.json` 包含 API Key 等敏感信息，已在 `.gitignore` 中排除，不要提交。
- 如果只需要导出脱水聊天文本供其他工具使用，使用 `--export-txt` 避免不必要的 API 费用。

## Configuration reference

完整配置字段参考 `config.json.example`。关键参数：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `chunk_size` | 100000 | 每分段最大字符数 |
| `sample_limit` | 5000 | 抽样目标条数 |
| `map_workers` | 5 | Map 阶段并发数 |
| `rate_limit_calls` | 14 | 每分钟最大 API 调用 |
| `temperature` | 0.2 | LLM 温度参数 |
| `max_tokens` | 8192 | LLM 最大输出 Token |

更多架构细节参见 [references/architecture.md](references/architecture.md)。
