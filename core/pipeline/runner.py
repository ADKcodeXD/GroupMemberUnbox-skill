"""
Headless Pipeline Runner — 不依赖 PyQt5，可在 CLI / Agent 环境下直接运行。

用法：
    from core.pipeline.runner import HeadlessPipelineRunner
    runner = HeadlessPipelineRunner(files, target_uin, config)
    result = runner.run()
"""
import os
import sys
import json
import threading
from .builder import build_graph


class HeadlessPipelineRunner:
    """无 GUI 依赖的 Pipeline 执行器。"""

    def __init__(self, files, target_uin, config, preloaded_state=None,
                 on_progress=None, on_preview=None):
        """
        Args:
            files:            QQ 聊天记录 JSON 文件路径列表
            target_uin:       目标人物 QQ 号
            config:           配置字典 (同 config.json 格式)
            preloaded_state:  可选，断点续传的 checkpoint 状态
            on_progress:      可选，进度回调 (percent: int, msg: str) -> None
            on_preview:       可选，阶段预览回调 (stage: str, content: str) -> None
        """
        self.files = files
        self.target_uin = target_uin
        self.config = config
        self.preloaded_state = preloaded_state
        self.stop_event = threading.Event()
        self.graph = build_graph()

        # 默认回调：打印到 stderr
        self._on_progress = on_progress or self._default_progress
        self._on_preview = on_preview or (lambda stage, content: None)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def stop(self):
        """发出停止信号。"""
        self.stop_event.set()

    def run(self) -> dict:
        """
        同步执行完整 Pipeline，返回结果字典。

        Returns:
            {
                "report":    str,   # Markdown 格式最终报告
                "skill_dir": str,   # 产出的 skill 目录路径（如有）
                "error":     str|None
            }
        """
        state = self._build_initial_state()

        try:
            for event in self.graph.stream(state, config={"recursion_limit": 50}):
                if self.stop_event.is_set():
                    self._save_checkpoint(state)
                    return {"report": "", "skill_dir": None,
                            "error": "任务已被用户终止。"}

                node_name = next(iter(event))
                updates = event[node_name]
                state.update(updates)

                self._save_checkpoint(state)

                # 错误处理
                if updates.get("error"):
                    return {"report": "", "skill_dir": None,
                            "error": updates["error"]}

                # 进度回调
                if "progress" in updates:
                    self._on_progress(
                        updates["progress"],
                        f"{node_name.capitalize()} 阶段完成"
                    )

                # 预览回调
                self._emit_previews(node_name, updates, state)

            return {
                "report": state.get("combined_report", ""),
                "skill_dir": state.get("skill_dir"),
                "error": None,
            }

        except Exception as exc:
            import traceback
            traceback.print_exc()
            return {"report": "", "skill_dir": None,
                    "error": f"Pipeline 运行异常: {exc}"}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_initial_state(self) -> dict:
        if self.preloaded_state:
            state = self.preloaded_state
            state["stop_event"] = self.stop_event
            state["callbacks"] = {
                "progress": self._on_progress,
                "preview": self._on_preview,
            }
            state["is_running"] = True
            return state

        return {
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
            "skill_dir": None,
            "is_running": True,
            "stop_event": self.stop_event,
            "callbacks": {
                "progress": self._on_progress,
                "preview": self._on_preview,
            },
            "current_stage": "Init",
            "progress": 0,
            "session_log_dir": "",
            "audit_count": 0,
            "tool_count": 0,
            "search_query": None,
            "search_results": None,
            "error": None,
        }

    @staticmethod
    def _save_checkpoint(state: dict):
        log_dir = state.get("session_log_dir")
        if not log_dir or not os.path.exists(log_dir):
            return

        serializable = {
            k: v for k, v in state.items()
            if k not in ("stop_event", "callbacks", "messages")
        }
        try:
            cp_path = os.path.join(log_dir, "checkpoint.json")
            with open(cp_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=4)
        except Exception as exc:
            print(f"[Runner] 保存检查点失败: {exc}", file=sys.stderr)

    def _emit_previews(self, node_name, updates, state):
        if node_name == "extract" and "chat_text" in updates:
            text = updates["chat_text"]
            preview = text[:3000] + ("..." if len(text) > 3000 else "")
            self._on_preview("raw_preview", preview)

        elif node_name == "merge" and "evidence_base" in updates:
            self._on_preview("evidence_base", updates["evidence_base"])

        elif node_name in ("audit", "refine") and "audit_opinion" in state:
            if node_name == "refine":
                msg = f"Agent 已优化证据库\n\n{state.get('evidence_base', '')}"
            else:
                msg = f"Agent 审计中...\n\n{state['audit_opinion']}"
            self._on_preview("evidence_base", msg)

        elif node_name == "reduce" and "reduce_results" in updates:
            for mod, content in updates["reduce_results"].items():
                self._on_preview(f"reduce_{mod}", content)

    @staticmethod
    def _default_progress(percent, msg):
        print(f"[{percent:3d}%] {msg}", file=sys.stderr)
