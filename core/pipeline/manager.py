import os
import json
import threading
from PyQt5.QtCore import QThread, pyqtSignal
from .builder import build_graph

class PipelineManager(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    stage_preview = pyqtSignal(str, str)
    
    def __init__(self, files, target_uin, config, preloaded_state=None):
        super().__init__()
        self.files = files
        self.target_uin = target_uin
        self.config = config
        self.preloaded_state = preloaded_state
        self._is_running = True
        self.stop_event = threading.Event()
        self.graph = build_graph()
        
    def stop(self):
        self._is_running = False
        self.stop_event.set()

    def save_checkpoint(self, state):
        """将状态持久化到磁盘"""
        log_dir = state.get("session_log_dir")
        if not log_dir or not os.path.exists(log_dir):
            return
            
        # 过滤掉无法序列化的对象
        serializable_state = {}
        for k, v in state.items():
            if k in ["stop_event", "callbacks", "messages"]: # messages 太大且由 chat_text 覆盖，不存入 json
                continue
            serializable_state[k] = v
            
        try:
            checkpoint_path = os.path.join(log_dir, "checkpoint.json")
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(serializable_state, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存检查点失败: {e}")

    def run(self):
        # 初始状态载入: 优先使用预加载的状态
        if self.preloaded_state:
            state = self.preloaded_state
            # 补全非序列化字段
            state["stop_event"] = self.stop_event
            state["callbacks"] = {
                "progress": self.progress.emit,
                "preview": self.stage_preview.emit
            }
            state["is_running"] = True
        else:
            state = {
                "files": self.files,
                "target_uin": self.target_uin,
                "config": self.config,
                "messages": [],
                "chat_text": "",
                "chunks": [],
                "map_results": [],
                "fidelity_results": [],
                "evidence_base": "",
                "audit_opinion": None,
                "reduce_results": {},
                "combined_report": "",
                "skill_dir": None,
                "is_running": True,
                "stop_event": self.stop_event,
                "callbacks": {
                    "progress": self.progress.emit,
                    "preview": self.stage_preview.emit
                },
                "current_stage": "Init",
                "progress": 0,
                "session_log_dir": "",
                "audit_count": 0,
                "error": None
            }
        
        try:
            # 使用流式执行以便获取中间状态
            for event in self.graph.stream(state, config={"recursion_limit": 50}):
                if self.stop_event.is_set():
                    self.error.emit("任务已被用户终止。")
                    self.save_checkpoint(state) # 即使终止也保存最后状态
                    return
                
                # event 格式为 {node_name: {updates}}
                node_name = next(iter(event))
                updates = event[node_name]
                
                # 重要：将节点更新合并到我们的全量状态中
                state.update(updates)
                
                # 每步持久化
                self.save_checkpoint(state)
                
                # 处理错误
                if "error" in updates and updates["error"]:
                    self.error.emit(updates["error"])
                    return
                
                # 发送进度信号
                if "progress" in updates:
                    stage_msg = f"{node_name.capitalize()} 阶段完成"
                    self.progress.emit(updates["progress"], stage_msg)
                
                # 发送预览信号
                if node_name == "extract" and "chat_text" in updates:
                    text = updates["chat_text"]
                    preview = text[:3000] + ("..." if len(text) > 3000 else "")
                    self.stage_preview.emit("raw_preview", preview)
                
                elif node_name == "merge" and "evidence_base" in updates:
                    self.stage_preview.emit("evidence_base", updates["evidence_base"])
                
                elif node_name in ["audit", "refine"] and "audit_opinion" in state:
                    msg = f"### 🛡️ Agent 审计中...\n\n{state['audit_opinion']}"
                    if node_name == "refine":
                        msg = f"### ✨ Agent 已优化证据库\n\n{state.get('evidence_base', '')}"
                    self.stage_preview.emit("evidence_base", msg)
                
                elif node_name == "reduce" and "reduce_results" in updates:
                    for mod, content in updates["reduce_results"].items():
                        self.stage_preview.emit(f"reduce_{mod}", content)
            
            # 结束后从累积的状态中提取最终结果
            final_res = {
                "report": state.get("combined_report", ""),
                "skill_dir": state.get("skill_dir")
            }
            self.finished.emit(json.dumps(final_res))
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"Pipeline 运行异常: {str(e)}")
