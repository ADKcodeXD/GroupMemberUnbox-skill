# Pipeline Architecture Reference

本文档描述群友炼化机的 LangGraph Pipeline 架构，供需要理解内部工作原理或排查问题时参考。

## Pipeline 流向

```
START → extract → map → merge ─┬─ (agent_mode=false) → reduce → skill → END
                                └─ (agent_mode=true)  → audit ─┬─ [SEARCH] → retrieve → audit
                                                                ├─ 审计未通过  → refine → audit
                                                                └─ 审计通过    → reduce → skill → END
```

## 各节点详解

### 0. Input Adapter (输入适配层)

- **目录**: `core/input_adapters/`
- **目标**:
  - 将不同平台的原始聊天记录统一映射为标准消息结构
  - 下游 `extract/map/merge/...` 只消费统一结构，不关心来源平台
- **当前实现**:
  - `qq_adapter.py`
- **扩展方式**:
  - 新平台只需新增 adapter，例如：
    - `weixin_adapter.py`
    - `discord_adapter.py`
    - `telegram_adapter.py`
  - 在 `registry.py` 注册后即可接入

统一消息结构核心字段：

- `timestamp`
- `sender.uin`
- `sender.name`
- `content.text`
- `system`
- `scene_tag`
- `source_platform`
- `source_file`
- `raw`

### 1. Extract (数据提取)

- **文件**: `core/pipeline/nodes/extract_node.py`
- **输入**: JSON 聊天记录文件列表 + 目标 QQ 号
- **处理**:
  1. 解析 JSON，按 `sender.uin` 匹配目标人物
  2. 提取目标人物发言及上下文（±N 条）
  3. 可选：智能均匀抽样（按时间分桶，每桶选字数最多的）
  4. 使用 jieba 进行 TF-IDF 关键词提取 + 语气助词分析
  5. 生成消息级索引与可选本地 embedding
  6. 生成高价值原话候选池
  7. 按 `chunk_size` 分段
- **输出**:
  - `chat_text`, `chunks[]`, `word_frequency`
  - `message_index_path`
  - `message_embedding_path`
  - `highlight_candidates_path`

### 2. Map (并行特征提取)

- **文件**: `core/pipeline/nodes/map_node.py`
- **策略**: 每个 chunk 并行发起 2 次 AI 调用:
  - **Knowledge Agent**: 提取 A-E 五类事实（硬性事实/状态/回忆/行为/喜好），标注可信度 1-5
  - **Fidelity Agent**: 提取高保真对话片段（保留原话，不做任何润色）
    - 当前实现会优先读取本地“高价值候选池”作为增强上下文
    - 可配置为本地 Ollama 模式（推荐 `qwen3:4b`），不可用时自动回退到线上主模型
- **并发**: `ThreadPoolExecutor(max_workers=map_workers*2)`
- **输出**: `map_results[]`, `fidelity_results[]`

### 3. Merge (跨切片验证汇总)

- **文件**: `core/pipeline/nodes/merge_node.py` → `merge_node()`
- **核心逻辑**:
  - 孤片惩罚 (One-Slice Penalty): 单切片事实降级
  - 跨向加成 (Multi-Slice Bonus): 多切片独立验证的事实升级
  - 矛盾仲裁: 时间线还原 + 语境分析
  - 语言指纹聚合
- **输出**: `evidence_base` (全景证据库)

### 4. Audit (Agent 深度审计) — 可选

- **文件**: `core/pipeline/nodes/merge_node.py` → `audit_node()`
- **触发条件**: `config.agent_mode = true`
- **能力**:
  - 审计证据库的真实性
  - 可发起 `[SEARCH: 关键词]` 检索原始聊天记录
  - 最多 3 轮审计 + 5 次工具调用
- **流转**: 审计通过 → reduce; 审计不通过 → refine → 再审计

### 5. Retrieve (证据检索工具)

- **文件**: `core/pipeline/nodes/merge_node.py` → `retrieve_node()`
- **功能**:
  - 优先使用本地 embedding 索引进行语义检索
  - 检索失败时回退到完整 `chat_text` 的正则搜索
- **限制**:
  - 语义检索默认 top-k 由配置控制
  - 字符串回退模式每次最多 10 条命中，每条带 ±5 行上下文

### 6. Refine (证据库修正)

- **文件**: `core/pipeline/nodes/merge_node.py` → `refine_node()`
- **功能**: 根据审计意见修正证据库

### 7. Reduce (六层模块生成)

- **文件**: `core/pipeline/nodes/reduce_node.py`
- **Prompt 来源**: `prompts/prompt_skill.md`
- **执行方式**:
  - 解析结构化 section：`SYSTEM`、全局规则、各层任务段
  - 将全局证据协议、高风险推断护栏、输入证据块统一注入每个层级调用
  - 并行生成 5 个中间层：
    1. `objective.md`
    2. `inference.md`
    3. `behavior.md`
    4. `memory.md`
    5. `style.md`
- **输出**:
  - `reduce_results`（5 个中间层结果）
  - `combined_report`（Reduce 阶段中间合并报告）

### 8. Skill (总控技能蒸馏)

- **文件**: `core/pipeline/nodes/skill_node.py`
- **Prompt 来源**: `prompts/prompt_skill.md`
- **执行方式**:
  - 读取 Reduce 阶段生成的 5 个层级结果
  - 单独调用 `LAYER_4_CHAT` 精炼 `chathistory.md`
  - 基于所有层级结果再生成总控 `SKILL.md`
  - 对已存在的层文件执行 Append-Only 追加
- **当前生成文件**:
  - `objective.md`
  - `inference.md`
  - `behavior.md`
  - `chathistory.md`
  - `memory.md`
  - `style.md`
  - `SKILL.md`
  - `evolution.md`
- **额外输出**:
  - `metadata.json`
  - `00_final_report.md`
  - `.skill` 压缩包

## 状态结构 (AgentState)

定义在 `core/pipeline/state.py`，关键字段:

| 字段 | 类型 | 说明 |
|------|------|------|
| `files` | `List[str]` | 输入 JSON 文件路径 |
| `target_uin` | `str` | 目标 QQ 号 |
| `config` | `Dict` | 运行时配置 |
| `chat_text` | `str` | 格式化后的完整聊天文本 |
| `chunks` | `List[str]` | 分段后的文本块 |
| `map_results` | `List[str]` | 每段的知识提取结果 |
| `fidelity_results` | `List[str]` | 每段的高保真片段 |
| `evidence_base` | `str` | 全景证据库 |
| `reduce_results` | `Dict[str,str]` | Reduce 阶段各层内容 |
| `combined_report` | `str` | 当前阶段聚合报告（Reduce/Skill 均可更新） |
| `word_frequency` | `Dict` | 词频与语气指纹统计 |
| `message_index_path` | `str` | 消息级索引文件路径 |
| `message_embedding_path` | `str` | 本地 embedding 缓存路径 |
| `highlight_candidates_path` | `str` | 高价值原话候选池路径 |
| `skill_dir` | `str` | 输出 skill 目录路径 |
| `session_log_dir` | `str` | 会话日志目录 |

## 断点续传机制

- 每个 Pipeline 节点完成后自动保存 `checkpoint.json` 到 `logs/<session>/`
- 恢复时加载 checkpoint 并跳过已完成的阶段
- 不可序列化的字段（`stop_event`, `callbacks`）在恢复时重新注入

## Prompt 模板

所有 prompt 存放在 `prompts/` 目录。

当前实际使用的 prompt 文件：

- `system_map.md`
- `prompt_map.md`
- `system_map_fidelity.md`
- `prompt_map_fidelity.md`
- `system_merge.md`
- `prompt_merge.md`
- `system_review.md`
- `prompt_skill.md`

说明：

- `prompt_skill.md` 是新的总控结构化 prompt，内部通过 `### [SECTION]` 划分模块。
- Reduce 与 Skill 两个节点都会解析 `prompt_skill.md`，但它们负责的 section 不同。
- 旧版 `prompt_resume.md / prompt_analysis.md / prompt_literary.md / prompt_profiling.md / system_reduce.md / system_profiling.md` 已废弃并删除。

## 本地检索层

当前新增的本地检索模块位于 `core/retrieval/`：

- `embed_index.py`
  - 构建消息级索引
  - 调本地 embedding 服务
- `highlight_selector.py`
  - 基于规则与向量多样性选择高价值原话候选
- `semantic_retrieve.py`
  - 审计阶段的语义检索
- `vector_store.py`
  - 纯 Python cosine 相似度搜索

Phase 1 默认设计原则：

- 不替代核心大模型分析
- 只增强“找证据”和“找原话”的能力
- embedding 不可用时自动回退，不中断主流程
- 默认可使用内置 embedding，无需额外服务
- 当 `embedding_enabled=true` 且 provider 为 `ollama` 时，如本地缺少对应模型，可自动调用 Ollama 拉取（可通过 `auto_pull_local_models` 控制）

## 成本预估口径

GUI 中的“预估费用”当前按以下口径展示：

- **计入**：远程 LLM 的输入 / 输出 token 成本
- **不计入**：本地 embedding、本地语义检索、本地 CPU/GPU 运行时间、电费

因此在启用本地检索后：

- 远程美元成本会更接近真实支付成本
- 但总耗时仍会受到本地 embedding 和本地检索影响
