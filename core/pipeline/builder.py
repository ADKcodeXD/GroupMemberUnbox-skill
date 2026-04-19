from langgraph.graph import StateGraph, START, END
from .state import AgentState
from .nodes.extract_node import extract_node
from .nodes.map_node import map_node
from .nodes.merge_node import merge_node, audit_node, refine_node, retrieve_node
from .nodes.reduce_node import reduce_node
from .nodes.skill_node import skill_node

def should_audit(state: AgentState):
    """判断是否需要执行审计逻辑"""
    if state["config"].get("agent_mode", False):
        return "audit"
    return "reduce"

def after_audit(state: AgentState):
    """审计后的流转逻辑：增加工具调用分支"""
    # 1. 检查是否触发了搜索工具
    if state.get("search_query"):
        return "retrieve"
    
    opinion = state.get("audit_opinion", "")
    count = state.get("audit_count", 0)
    
    # 2. 检查是否审计通过
    if "【审计通过" in opinion or count >= 3:
        return "reduce"
    
    # 3. 否则进入修正环节
    return "refine"

def build_graph():
    """构建 LangGraph 状态图"""
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("extract", extract_node)
    workflow.add_node("map", map_node)
    workflow.add_node("merge", merge_node)
    workflow.add_node("audit", audit_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("refine", refine_node)
    workflow.add_node("reduce", reduce_node)
    workflow.add_node("skill", skill_node)
    
    # 构建边
    workflow.add_edge(START, "extract")
    workflow.add_edge("extract", "map")
    workflow.add_edge("map", "merge")
    
    # 核心 Agent 逻辑
    workflow.add_conditional_edges(
        "merge",
        should_audit,
        {
            "audit": "audit",
            "reduce": "reduce"
        }
    )
    
    workflow.add_conditional_edges(
        "audit",
        after_audit,
        {
            "retrieve": "retrieve",
            "refine": "refine",
            "reduce": "reduce"
        }
    )
    
    workflow.add_edge("retrieve", "audit")  # 检索后返回审计
    workflow.add_edge("refine", "audit")    # 修正后返回审计
    workflow.add_edge("reduce", "skill")
    workflow.add_edge("skill", END)
    
    return workflow.compile()
