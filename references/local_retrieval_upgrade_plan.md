# 本地高价值原话与语义审计改造方案

本文档给出一套**可渐进落地**的改造方案，目标是在**不牺牲现有大模型证据提取质量**的前提下，用本地 embedding/检索能力替换当前成本高、效果弱的“原话筛选”和“字符串审计检索”链路。

适用前提：

- 引入输入适配层，不将 pipeline 绑定在 QQ JSON 结构上
- 保留 `map_node` 中的大参数模型 `knowledge` 提取
- 保留 `merge / reduce / skill` 以大模型为主
- 优先本地化：
  - 高价值原话筛选
  - 审计检索
  - 候选证据召回

---

## 1. 当前问题

当前 pipeline 的主要问题不是“分析能力不够”，而是**找证据的方式过贵、过弱**：

1. `map_node` 的 `fidelity` 依赖 LLM 直接从 chunk 里摘“高价值原话”
   - 成本高
   - 稳定性差
   - 容易漏掉跨 chunk 的重复模式和代表性句子

2. `retrieve_node` 依赖字符串 / 正则搜索
   - 同义表达召回弱
   - 错别字、口语变体、黑话召回差
   - 审计模型一旦 query 写得不准，检索就失效

3. “原话候选池”没有统一索引
   - fidelity、audit、chat history 三个环节都在重复找材料
   - 没有缓存、没有向量复用

---

## 2. 目标

改造后的目标：

1. **高价值原话**主要通过本地 embedding 检索、聚类和打分选出
2. **审计检索**从字符串搜索升级为语义检索
3. **大模型只做高价值理解**
   - 结构化证据提取
   - 证据归并
   - 推断与写作
4. 保持现有功能完整：
   - 不移除 Agent 审计模式
   - 不移除 `fidelity_results`
   - 不破坏现有日志、预览、checkpoint、最终产物结构

---

## 3. 总体架构

建议新增一层“本地检索层”：

```text
input_adapter
  └─ 不同平台原始记录 -> 统一消息结构

extract
  ├─ 原有：聊天提取、format、jieba统计
  └─ 新增：消息级索引 + embedding 建库

map
  ├─ knowledge：继续走大参数模型
  └─ fidelity：改为“本地候选召回 + 可选模型精炼”

merge
  └─ 保持大模型归并

audit/retrieve
  └─ 改为本地语义检索返回证据包

reduce/skill
  └─ 继续以大模型为主，消费更高质量的 evidence/highlights
```

说明：

- 输入适配层与本地检索层是正交的
- 后续新增微信 / Discord / Telegram 时，不应修改检索逻辑，只新增 adapter

---

## 4. 分阶段落地

### Phase 1：最小风险版本

目标：**先把检索能力建起来，不改核心分析主链**

范围：

1. 新增消息级索引与 embedding
2. 将 `retrieve_node` 从字符串搜索升级为语义检索
3. 新增本地“高价值原话候选池”
4. `map_node` 暂时仍保留原有 `fidelity` LLM 调用，作为对照组

收益：

- 审计效果显著提升
- 后面改 fidelity 有基础设施可复用
- 风险低，容易回滚

### Phase 2：fidelity 半本地化

目标：**把最贵的“原话筛选”从 LLM 盲摘改成本地召回主导**

范围：

1. 本地规则召回高信号消息
2. embedding 聚类去重
3. 生成 `high_value_candidates`
4. 可选：再用小模型或大模型从候选中精炼 `fidelity_results`

收益：

- 明显降低 map 阶段调用成本
- 候选池更稳定
- 为 chathistory 审校提供统一语料池

### Phase 3：审计结构化升级

目标：让审计模型不再只吐字符串 query，而是输出**结构化检索意图**

范围：

1. `audit_node` 输出 JSON 查询意图
2. `retrieve_node` 支持多 query、多条件检索
3. 返回带相似度、上下文、命中理由的证据包

收益：

- Agent 审计真正闭环
- 后续可以支持更复杂的“证据反驳”和“定向核验”

---

## 5. 建议新增模块

建议新增目录：

```text
core/
  retrieval/
    __init__.py
    schemas.py
    embed_index.py
    vector_store.py
    highlight_selector.py
    semantic_retrieve.py
```

### `core/retrieval/schemas.py`

定义核心数据结构：

- `IndexedMessage`
- `RetrievalHit`
- `HighlightCandidate`
- `AuditQuery`

### `core/retrieval/embed_index.py`

负责：

- 从 `messages` 生成消息级索引
- 文本标准化
- embedding 批量生成
- embedding 缓存落盘

### `core/retrieval/vector_store.py`

负责：

- 向量相似度搜索
- top-k 召回
- 可选时间过滤、target 过滤、来源过滤

第一版可先用 `numpy + cosine similarity`。
后续如数据量变大再接 `faiss`。

### `core/retrieval/highlight_selector.py`

负责：

- 规则召回高信号消息
- 多特征打分
- 去重 / 聚类
- 输出高价值原话候选池

### `core/retrieval/semantic_retrieve.py`

负责：

- 将审计 query 转 embedding
- 执行语义检索
- 拼装上下文证据包

---

## 6. 数据结构设计

### 6.1 消息索引

建议产物：

- `message_index.jsonl`
- `message_embeddings.json` 或 `message_embeddings.npy`

`IndexedMessage` 建议字段：

```json
{
  "msg_id": "hash_or_seq_id",
  "sender_uin": "123456",
  "timestamp": "2025-01-01 23:14:52",
  "date": "2025-01-01",
  "hour": 23,
  "is_target": true,
  "text": "原始消息文本",
  "normalized_text": "归一化文本",
  "context_before": ["..."],
  "context_after": ["..."],
  "features": {
    "char_len": 18,
    "contains_money": false,
    "contains_work": true,
    "contains_relationship": false,
    "contains_health": false,
    "contains_self_mock": true,
    "contains_attack": false,
    "contains_help": false,
    "punctuation_score": 0.4,
    "emotion_score": 0.7,
    "late_night": true
  }
}
```

### 6.2 检索命中

```json
{
  "msg_id": "xxx",
  "score": 0.84,
  "text": "命中原话",
  "timestamp": "2025-01-01 23:14:52",
  "context": "上下文拼接后的文本",
  "hit_reason": ["semantic_match", "late_night", "self_mock"]
}
```

### 6.3 高价值候选

```json
{
  "msg_id": "xxx",
  "priority_score": 0.91,
  "tags": ["self_mock", "work_stress", "late_night"],
  "cluster_id": 12,
  "representative": true,
  "text": "原话",
  "context": "上下文"
}
```

---

## 7. 对现有节点的改动建议

### 7.1 `extract_node.py`

新增能力：

1. 生成消息级索引
2. 调本地 embedding 服务生成向量
3. 落盘索引与 embedding
4. 预计算规则特征

新增状态字段建议：

- `message_index_path`
- `message_embedding_path`
- `highlight_candidates_path`

说明：

- 不改变现有 `chat_text / chunks / word_frequency`
- 只是增加后续可复用的检索底座

### 7.2 `map_node.py`

#### Phase 1

先不动 `knowledge`。

`fidelity` 保留旧逻辑，但额外允许读取本地候选池，作为 prompt 上下文增强：

- 原来：直接给 chunk
- 改后：给 chunk + 本地候选摘要

#### Phase 2

支持配置开关：

- `fidelity_mode = remote`
- `fidelity_mode = local_candidates`
- `fidelity_mode = local_candidates_plus_llm`

推荐默认：

- 先做 `local_candidates_plus_llm`

即：

1. 本地筛出候选
2. 大模型只在候选里挑最有价值的原话并加标签说明

这样能降成本，又不完全失去模型判断力。

### 7.3 `merge_node.py / audit_node.py / retrieve_node.py`

重点改 `retrieve_node`。

#### 旧逻辑

- query -> regex -> 聊天全文逐行搜索

#### 新逻辑

- query -> embedding
- 在消息向量库中检索 top-k
- 可附加筛选：
  - 仅 target 发言
  - 指定时间范围
  - 指定 evidence type 偏好
- 返回结构化命中包

推荐兼容策略：

- 若本地索引不可用，则回退到字符串搜索
- 这样不会破坏原有功能完整性

### 7.4 `prompt/system_review.md`

后续应调整审计提示：

- 从输出 `[SEARCH: xxx]`
- 升级为输出结构化检索请求，如：

```json
{
  "queries": [
    {
      "intent": "验证其是否长期熬夜",
      "query": "目标人物关于熬夜、失眠、凌晨活跃、作息紊乱的发言",
      "target_only": true,
      "top_k": 8
    }
  ]
}
```

第一阶段可先保留 `[SEARCH: xxx]` 兼容格式，后续再升级。

---

## 8. 本地模型与工具建议

### 8.1 Embedding

推荐优先级：

1. `qwen3-embedding:0.6b`
2. `qwen3-embedding:4b`

建议原因：

- 中文支持较好
- 本地部署相对轻
- 足够胜任聊天语义召回

适合部署方式：

- Ollama 本地 API

### 8.2 Reranker

第一阶段可不加。

如后续需要：

- 加本地 reranker 对 top-k 做二次排序
- 用于审计证据更精准排序

### 8.3 本地小模型

你的判断是对的：

- 不建议本地小模型接管核心证据抽取
- 但可用于：
  - 候选摘要标签
  - 低成本初步过滤
  - JSON 格式化

---

## 9. 配置项建议

建议新增配置项：

```json
{
  "embedding_enabled": true,
  "embedding_provider": "ollama",
  "embedding_model": "qwen3-embedding:0.6b",
  "fidelity_mode": "local_candidates_plus_llm",
  "semantic_retrieval_enabled": true,
  "semantic_retrieval_top_k": 8,
  "highlight_candidate_limit": 300,
  "highlight_cluster_enabled": true,
  "highlight_target_only": true
}
```

---

## 10. 日志与缓存产物

建议新增落盘文件：

```text
logs/<session>/
  01b_message_index.jsonl
  01c_message_embeddings.json
  01d_highlight_candidates.jsonl
  retrieve_semantic_1.json
  retrieve_semantic_2.json
```

说明：

- embedding 必须缓存，否则成本会从“API成本”变成“本地推理成本”
- 后续可基于消息 hash 做增量更新

---

## 11. 兼容性与回滚策略

必须保证以下兼容原则：

1. 本地 embedding 失败时，不影响主流程
   - 回退到原有字符串搜索

2. fidelity 新逻辑默认通过配置开关启用
   - 可随时切回旧方案

3. 不修改现有最终产物文件名
   - `SKILL.md`
   - `objective.md`
   - `inference.md`
   - `behavior.md`
   - `chathistory.md`
   - `memory.md`
   - `style.md`

4. 不移除现有日志和 preview 事件

---

## 12. 推荐执行顺序

建议按以下顺序实施：

### Step 1

新增本地索引与 embedding 基础设施：

- `core/retrieval/*`
- `extract_node` 落盘消息索引与 embedding

### Step 2

改造 `retrieve_node`：

- 优先 semantic search
- fallback 到 regex search

### Step 3

新增 `highlight_selector`：

- 生成高价值原话候选池

### Step 4

让 `map_node` 的 fidelity 消费候选池：

- 先做 `local_candidates_plus_llm`

### Step 5

再升级 audit prompt 为结构化检索意图

---

## 13. 我建议先执行的版本

如果只做一版可控改造，我建议：

### 本次实施范围

1. 新增本地 embedding 索引
2. 语义检索版 `retrieve_node`
3. 高价值原话候选池生成
4. `map_node` fidelity 改成“候选池增强版”

### 暂不做

1. 不把 `knowledge` 提取本地化
2. 不强依赖 reranker
3. 不重写 merge/reduce/skill 主逻辑

这是**收益最大、风险最低、最符合当前项目结构**的一版。
