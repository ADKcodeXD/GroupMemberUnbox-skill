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
    stage_preview_stream = pyqtSignal(str, str)
    
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
                "preview": self.stage_preview.emit,
                "preview_stream": self.stage_preview_stream.emit
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
                "word_frequency": {},
                "message_index_path": "",
                "message_embedding_path": "",
                "highlight_candidates_path": "",
                "local_embedding_error": None,
                "session_log_dir": "",
                "start_time": "",
                "stop_event": self.stop_event,
                "callbacks": {
                    "progress": self.progress.emit,
                    "preview": self.stage_preview.emit,
                    "preview_stream": self.stage_preview_stream.emit
                },
                "is_running": True
            }

        # 运行图
        try:
            for node_name, node_func in self.graph:
                if not self._is_running:
                    break
                
                # 特殊逻辑：根据 checkpoint 跳过已完成阶段
                # 只有当 state 中已有对应结果且不是从外部 preloaded 强制覆盖时才跳过
                if node_name == "Extract" and state.get("chat_text"):
                    self.progress.emit(10, "跳过提取阶段，使用缓存数据...")
                    continue
                if node_name == "Map" and (state.get("map_results") and len(state.get("map_results")) > 0):
                    self.progress.emit(65, "跳过分片映射阶段，使用已保存的分片结果...")
                    continue
                if node_name == "Merge" and state.get("evidence_base"):
                    self.progress.emit(75, "跳过合并阶段...")
                    continue

                # 执行代码
                self.progress.emit(state.get("progress", 0), f"正在进入阶段: {node_name}...")
                result = node_func(state)
                
                # 更新状态
                state.update(result)
                
                # 自动保存检查点
                self.save_checkpoint(state)

            if self._is_running:
                self.finished.emit(json.dumps({
                    "report": state.get("combined_report", "分析中断或无结果"),
                    "skill_dir": state.get("session_log_dir", "")
                }))
            else:
                self.error.emit("任务已被用户停止")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"管道运行错误: {str(e)}")
