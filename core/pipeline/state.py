from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated
import operator

class AgentState(TypedDict):
    # === 输入与配置 ===
    files: List[str]
    target_uin: str
    config: Dict[str, Any]
    
    # === 中间产物 ===
    messages: List[Dict[str, Any]]
    chat_text: str
    chunks: List[str]
    
    # Map 结果: (索引, 结果文本)
    map_results: List[Optional[str]]
    fidelity_results: List[Optional[str]]
    
    # Merge 结果
    evidence_base: str
    audit_opinion: Optional[str]
    
    # Reduce 结果
    reduce_results: Dict[str, str]
    combined_report: str
    word_frequency: Dict[str, Any]
    message_index_path: str
    message_embedding_path: str
    highlight_candidates_path: str
    local_embedding_error: Optional[str]

    # Skill 结果
    skill_dir: Optional[str]
    
    # === 状态控制 ===
    is_running: bool
    stop_event: Any  # threading.Event 实时信号
    callbacks: Dict[str, Any]  # UI 回调函数 (progress, preview 等)
    current_stage: str
    progress: int
    session_log_dir: str
    audit_count: int
    tool_count: int  # 记录工具调用次数，防止无限循环
    search_query: Optional[str]
    search_results: Optional[str]
    error: Optional[str]
