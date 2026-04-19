import os
import json
import markdown
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QFileDialog, QTextBrowser, QProgressBar, QMessageBox, 
                             QTabWidget, QSplitter, QCheckBox, QComboBox,
                             QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from core.data_processor import extract_chat_context, format_for_ai
from core.pipeline.utils import estimate_analysis, TestApiThread
from core.pipeline.manager import PipelineManager
from core.config import load_config, save_config, API_PRESETS
from .settings_dialog import SettingsDialog
from .styles import DARK_THEME_CSS, REPORT_HTML_STYLE

class ProfilerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("群友炼化机")
        self.resize(1500, 900)
        self.selected_files = []
        self.config = load_config()
        self.setStyleSheet(DARK_THEME_CSS)
        self.initUI()
        self._sync_config_to_ui()
        
    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # === 左侧面板：控制区 ===
        left_panel = QWidget()
        left_panel.setMaximumWidth(380)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 15, 10)
        left_layout.setSpacing(12)
        
        lbl_title = QLabel("🔥 群友炼化控制台")
        lbl_title.setObjectName("title")
        left_layout.addWidget(lbl_title)
        
        # 文件选择
        self.btn_select_files = QPushButton("📁 选择 JSON 记录文件")
        self.btn_select_files.clicked.connect(self.select_files)
        left_layout.addWidget(self.btn_select_files)
        
        self.lbl_files = QLabel("未选择文件")
        self.lbl_files.setWordWrap(True)
        left_layout.addWidget(self.lbl_files)
        
        # QQ号
        left_layout.addWidget(QLabel("🎯 目标人物 QQ 号:"))
        self.input_qq = QLineEdit()
        self.input_qq.setPlaceholderText("输入 uin，如 1778531385")
        left_layout.addWidget(self.input_qq)
        
        # 选项
        self.chk_only_target = QCheckBox("仅提取目标人发言 (无上下文)")
        left_layout.addWidget(self.chk_only_target)
        
        self.chk_sample = QCheckBox("开启智能均匀抽样 (字数优先)")
        self.chk_sample.setChecked(True)
        left_layout.addWidget(self.chk_sample)

        self.chk_agent = QCheckBox("🧠 开启 Agent 深度审计 (耗时增两倍)")
        self.chk_agent.setToolTip("在汇总阶段开启自动推理与反复验证，显著提升准确度但增加耗时和费用。")
        left_layout.addWidget(self.chk_agent)
        
        # API 快捷设置
        left_layout.addSpacing(5)
        left_layout.addWidget(QLabel("🌐 API 镜像站:"))
        self.combo_api_preset = QComboBox()
        for name in API_PRESETS:
            self.combo_api_preset.addItem(name)
        self.combo_api_preset.currentTextChanged.connect(self._on_preset_changed)
        left_layout.addWidget(self.combo_api_preset)
        
        self.input_api_base = QLineEdit()
        self.input_api_base.setPlaceholderText("API Base URL")
        left_layout.addWidget(self.input_api_base)
        
        left_layout.addWidget(QLabel("🔑 API Key:"))
        self.input_api_key = QLineEdit()
        self.input_api_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        left_layout.addWidget(self.input_api_key)
        
        self.input_model = QLineEdit()
        left_layout.addWidget(self.input_model)
        
        self.btn_test_api = QPushButton("⚡ 测试 LLM 连通性")
        self.btn_test_api.setObjectName("btn_export") # 使用绿色风格
        self.btn_test_api.clicked.connect(self.test_api)
        left_layout.addWidget(self.btn_test_api)
        
        left_layout.addStretch()
        
        # 按钮区
        self.btn_settings = QPushButton("⚙️ 高级设置")
        self.btn_settings.setObjectName("btn_export")
        self.btn_settings.clicked.connect(self.open_settings)
        left_layout.addWidget(self.btn_settings)
        
        self.btn_start = QPushButton("顷刻炼化")
        self.btn_start.clicked.connect(self.start_analysis)
        left_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("🛑 停止任务")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_analysis)
        self.btn_stop.setStyleSheet("QPushButton:enabled { background-color: #f38ba8; color: #11111b; font-weight: bold; }")
        left_layout.addWidget(self.btn_stop)
        
        self.btn_export_txt = QPushButton("📄 仅导出脱水 TXT")
        self.btn_export_txt.setObjectName("btn_export")
        self.btn_export_txt.clicked.connect(self.export_txt)
        left_layout.addWidget(self.btn_export_txt)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        left_layout.addWidget(self.progress_bar)
        
        self.lbl_status = QLabel("系统就绪待命")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        left_layout.addWidget(self.lbl_status)
        
        # === 右侧面板：结果展示 ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        # Tab 1: 最终报告
        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.setHtml(REPORT_HTML_STYLE + "<h2 style='text-align:center; margin-top:200px; color:#585b70;'>报告将在此展示</h2>")
        self.tabs.addTab(self.report_browser, "📊 最终报告")
        
        # Tab 2: 原文预览（截取版）
        self.raw_preview_browser = QTextBrowser()
        self.raw_preview_browser.setFontFamily("Consolas")
        self.tabs.addTab(self.raw_preview_browser, "💬 原文预览")
        
        # Tab 3: 实时阶段输出
        self.stage_browser = QTextBrowser()
        self.stage_browser.setFontFamily("Consolas")
        self.stage_browser.setHtml("<p style='color:#585b70; text-align:center; margin-top:100px;'>分析启动后，各阶段的 LLM 输出将在此实时展示</p>")
        self.tabs.addTab(self.stage_browser, "🔍 实时阶段输出")
        
        # Tab 4: 简历模块
        self.resume_browser = QTextBrowser()
        self.resume_browser.setOpenExternalLinks(True)
        self.tabs.addTab(self.resume_browser, "📋 简历")
        
        # Tab 5: 分析模块
        self.analysis_browser = QTextBrowser()
        self.analysis_browser.setOpenExternalLinks(True)
        self.tabs.addTab(self.analysis_browser, "🔬 解剖")
        
        # Tab 6: 文学模块
        self.literary_browser = QTextBrowser()
        self.literary_browser.setOpenExternalLinks(True)
        self.tabs.addTab(self.literary_browser, "📖 文学")
        
        right_layout.addWidget(self.tabs)

        # === 历史记录面板 (最右侧) ===
        history_panel = QWidget()
        history_panel.setMaximumWidth(280)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(10, 0, 0, 0)
        
        lbl_hist = QLabel("📜 历史会话")
        lbl_hist.setObjectName("title")
        history_layout.addWidget(lbl_hist)
        
        self.list_history = QListWidget()
        self.list_history.itemDoubleClicked.connect(self.load_selected_history)
        history_layout.addWidget(self.list_history)
        
        self.btn_refresh_hist = QPushButton("🔄 刷新历史")
        self.btn_refresh_hist.clicked.connect(self.scan_history)
        history_layout.addWidget(self.btn_refresh_hist)
        
        self.btn_resume = QPushButton("⏯️ 继续上次任务")
        self.btn_resume.clicked.connect(self.resume_selected_history)
        history_layout.addWidget(self.btn_resume)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.addWidget(history_panel)
        splitter.setSizes([350, 870, 280])
        
        # 初始扫描历史
        self.scan_history()
    
    def scan_history(self):
        """扫描 logs 文件夹下的 session"""
        self.list_history.clear()
        if not os.path.exists("logs"):
            return
            
        sessions = []
        for d in os.listdir("logs"):
            path = os.path.join("logs", d)
            if os.path.isdir(path):
                cp_path = os.path.join(path, "checkpoint.json")
                if os.path.exists(cp_path):
                    # 获取修改时间
                    mtime = os.path.getmtime(cp_path)
                    sessions.append((d, mtime, path))
        
        # 按时间排序
        sessions.sort(key=lambda x: x[1], reverse=True)
        
        for d, mtime, path in sessions:
            item = QListWidgetItem(d)
            item.setData(Qt.UserRole, path)
            self.list_history.addItem(item)

    def load_selected_history(self):
        """双击加载历史查看"""
        item = self.list_history.currentItem()
        if not item: return
        log_dir = item.data(Qt.UserRole)
        
        # 如果存在最终报告，则显示
        report_path = os.path.join(log_dir, "00_final_report.md")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                html = markdown.markdown(f.read())
                self.report_browser.setHtml(REPORT_HTML_STYLE + html)
                self.tabs.setCurrentIndex(0)
        else:
            self.tabs.setCurrentIndex(2)
            self.stage_browser.append(f"<p style='color:#f9e2af;'>会话 [{os.path.basename(log_dir)}] 未完成，可以点击“继续上次任务”。</p>")

    def resume_selected_history(self):
        """断点续传"""
        item = self.list_history.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先从列表中选择一个要恢复的会话。")
            return
            
        log_dir = item.data(Qt.UserRole)
        cp_path = os.path.join(log_dir, "checkpoint.json")
        
        try:
            with open(cp_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            # 基础验证
            if not state.get("target_uin"):
                raise ValueError("Checkpoint 文件损坏: 缺少目标 QQ 号")
            
            # 自动填回 UI
            self.input_qq.setText(state["target_uin"])
            self.config = state.get("config", self.config)
            self._sync_config_to_ui()
            
            # 启动
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.progress_bar.setValue(state.get("progress", 0))
            self.lbl_status.setText(f"正在恢复会话: {state.get('current_stage', '未知阶段')}")
            
            self.tabs.setCurrentIndex(2)
            self.stage_browser.append(f"<hr><b style='color:#fab387;'>[断点续传启动: {os.path.basename(log_dir)}]</b>")
            
            self.thread = PipelineManager(None, state["target_uin"], self.config, preloaded_state=state)
            self.thread.progress.connect(self.update_progress)
            self.thread.finished.connect(self.on_analysis_finished)
            self.thread.error.connect(self.on_analysis_error)
            self.thread.stage_preview.connect(self.on_stage_preview)
            self.thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"无法加载存档: {str(e)}")
    
    def _sync_config_to_ui(self):
        """将 config 同步到 UI 控件"""
        cfg = self.config
        self.input_api_base.setText(cfg.get("api_base", ""))
        self.input_api_key.setText(cfg.get("api_key", ""))
        self.input_model.setText(cfg.get("model", "gemini-3-flash-preview"))
        self.chk_only_target.setChecked(cfg.get("only_target", False))
        self.chk_sample.setChecked(cfg.get("sample_enabled", True))
        self.chk_agent.setChecked(cfg.get("agent_mode", False))
        
        preset = cfg.get("api_preset", "本地 (AIStudioToAPI)")
        idx = self.combo_api_preset.findText(preset)
        if idx >= 0:
            self.combo_api_preset.setCurrentIndex(idx)
    
    def _sync_ui_to_config(self):
        """将 UI 控件的值写回 config"""
        self.config["api_base"] = self.input_api_base.text().strip()
        self.config["api_key"] = self.input_api_key.text().strip()
        self.config["model"] = self.input_model.text().strip()
        self.config["only_target"] = self.chk_only_target.isChecked()
        self.config["sample_enabled"] = self.chk_sample.isChecked()
        self.config["agent_mode"] = self.chk_agent.isChecked()
        self.config["api_preset"] = self.combo_api_preset.currentText()
    
    def _on_preset_changed(self, name):
        url = API_PRESETS.get(name, "")
        if name != "自定义" and url:
            self.input_api_base.setText(url)

    def test_api(self):
        """测试 API 连通性"""
        self._sync_ui_to_config()
        if not self.config["api_key"]:
            QMessageBox.warning(self, "提示", "请先输入 API Key")
            return
            
        self.btn_test_api.setEnabled(False)
        self.btn_test_api.setText("⌛ 正在测试...")
        self.lbl_status.setText("正在测试 API 连通度...")
        
        self.tabs.setCurrentIndex(2) # 切换到实时预览槽位
        self.stage_browser.append("<hr><b style='color:#89b4fa;'>[API 测试启动]</b>")
        
        self.test_thread = TestApiThread(self.config)
        self.test_thread.finished.connect(self.on_test_finished)
        self.test_thread.start()

    def on_test_finished(self, success, content):
        self.btn_test_api.setEnabled(True)
        self.btn_test_api.setText("⚡ 测试 LLM 连通性")
        
        if success:
            self.lbl_status.setText("API 测试成功！")
            self.stage_browser.append(f"<p style='color:#a6e3a1;'>✅ 连通成功！LLM 回复：</p><blockquote style='color:#cdd6f4;'>{content}</blockquote>")
        else:
            self.lbl_status.setText("API 测试失败")
            self.stage_browser.append(f"<p style='color:#f38ba8;'>❌ 连通失败！错误信息：</p><code style='color:#f38ba8;'>{content}</code>")
        
        # 自动滚动到底部
        scrollbar = self.stage_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def open_settings(self):
        self._sync_ui_to_config()
        dialog = SettingsDialog(self.config, self)
        if dialog.exec_():
            self.config = dialog.get_config()
            self._sync_config_to_ui()
        
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 JSON 文件", "", "JSON Files (*.json)")
        if files:
            self.selected_files = files
            file_names = [os.path.basename(f) for f in files]
            self.lbl_files.setText(f"已选 {len(files)} 个文件:\n{', '.join(file_names)[:100]}...")
            
    def export_txt(self):
        if not self.selected_files:
            QMessageBox.warning(self, "错误", "请选择至少一个 JSON 文件！")
            return
        target_uin = self.input_qq.text().strip()
        if not target_uin:
            QMessageBox.warning(self, "错误", "请输入目标 QQ 号！")
            return
            
        save_path, _ = QFileDialog.getSaveFileName(self, "保存 TXT", f"聊天提取_{target_uin}.txt", "Text Files (*.txt)")
        if not save_path:
            return
            
        self.btn_export_txt.setEnabled(False)
        self.lbl_status.setText("正在提取...")
        QApplication.processEvents()
        
        try:
            only_target = self.chk_only_target.isChecked()
            sample = self.chk_sample.isChecked()
            sample_limit = self.config.get("sample_limit", 5000)
            context_window = self.config.get("context_window", 2)
                
            messages = extract_chat_context(self.selected_files, target_uin, only_target, sample, sample_limit, context_window)
            if not messages:
                QMessageBox.warning(self, "提示", "未找到记录。")
            else:
                chat_text = format_for_ai(messages, target_uin, only_target)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(chat_text)
                # 只预览前3000字
                preview = chat_text[:3000] + (f"\n\n... (共 {len(chat_text)} 字符)" if len(chat_text) > 3000 else "")
                self.raw_preview_browser.setPlainText(preview)
                self.tabs.setCurrentIndex(1)
                QMessageBox.information(self, "成功", f"导出 {len(messages)} 条记录到 {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))
            
        self.btn_export_txt.setEnabled(True)
        self.lbl_status.setText("就绪")

    def start_analysis(self):
        if not self.selected_files:
            QMessageBox.warning(self, "提示", "请选择至少一个 JSON 文件。")
            return
        if not self.input_qq.text().strip():
            QMessageBox.warning(self, "提示", "请填写目标 QQ 号。")
            return
        if not self.input_api_key.text().strip():
            QMessageBox.warning(self, "提示", "请填写 API Key。")
            return
        
        self._sync_ui_to_config()
        
        # === 预估阶段 ===
        self.lbl_status.setText("正在预估分析规模...")
        QApplication.processEvents()
        
        try:
            only_target = self.config.get("only_target", False)
            sample = self.config.get("sample_enabled", True)
            sample_limit = self.config.get("sample_limit", 5000)
            context_window = self.config.get("context_window", 2)
            target_uin = self.input_qq.text().strip()
            
            messages = extract_chat_context(self.selected_files, target_uin, only_target, sample, sample_limit, context_window)
            if not messages:
                QMessageBox.warning(self, "提示", f"未找到 QQ 号 {target_uin} 的聊天记录。")
                return
            
            chat_text = format_for_ai(messages, target_uin, only_target)
            est = estimate_analysis(len(chat_text), self.config)
            
            reply = QMessageBox.question(
                self, "分析预估",
                f"📊 数据概况：\n"
                f"  • 消息条数: {len(messages)}\n"
                f"  • 文本总长: {len(chat_text):,} 字符\n"
                f"  • 预计分段: {est['num_chunks']} 块\n\n"
                f"⚡ 资源消耗预估：\n"
                f"  • API 调用总次数: ~{est['total_api_calls']} 次\n"
                f"  • 预计输入 Token: ~{est['total_in_tokens']} K\n"
                f"  • 预计输出 Token: ~{est['total_out_tokens']} K\n"
                f"  • 预计耗时: ~{est['estimated_minutes']} 分钟\n\n"
                f"💰 预估费用：\n"
                f"  • 约 ${est['estimated_cost']} USD\n\n"
                f"是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                self.lbl_status.setText("已取消")
                return
        except Exception as e:
            QMessageBox.critical(self, "预估失败", str(e))
            return
            
        # === 启动分析 ===
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.report_browser.setHtml(REPORT_HTML_STYLE + "<h2 style='text-align:center; margin-top:200px;'>🔥 正在炼化...</h2>")
        self.raw_preview_browser.clear()
        self.stage_browser.clear()
        self.resume_browser.clear()
        self.analysis_browser.clear()
        self.literary_browser.clear()
        self.tabs.setCurrentIndex(2)  # 切到实时阶段输出tab
        self._stage_log = []
        
        self.thread = PipelineManager(self.selected_files, target_uin, self.config)
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.on_analysis_finished)
        self.thread.error.connect(self.on_analysis_error)
        self.thread.stage_preview.connect(self.on_stage_preview)
        self.thread.start()

    def update_progress(self, val, text):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(text)
    
    def on_stage_preview(self, stage_name, content):
        """接收实时阶段预览"""
        if stage_name == "raw_preview":
            self.raw_preview_browser.setPlainText(content)
            return
        
        if stage_name == "extract_stats":
            html = markdown.markdown(content)
            self.stage_browser.append(f"<hr>{html}")
            return
        
        if stage_name == "evidence_base":
            html = markdown.markdown(content)
            self.stage_browser.append(f"<hr><h3 style='color:#a6e3a1;'>📦 全景证据库已生成</h3>{html}")
            return
        
        if stage_name.startswith("reduce_"):
            module = stage_name.replace("reduce_", "")
            html = markdown.markdown(content)
            styled = REPORT_HTML_STYLE + html
            
            if module == "resume":
                self.resume_browser.setHtml(styled)
            elif module == "analysis":
                self.analysis_browser.setHtml(styled)
            elif module == "literary":
                self.literary_browser.setHtml(styled)
            
            self.stage_browser.append(f"<hr><h3 style='color:#89b4fa;'>✅ {module} 模块完成</h3>")
            return
        
        if stage_name.startswith("map_chunk_"):
            self.stage_browser.append(f"<pre style='color:#bac2de; font-size:12px; white-space:pre-wrap;'>{content}</pre>")
            # 自动滚动到底部
            scrollbar = self.stage_browser.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        
    def stop_analysis(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.stop()
            self.btn_stop.setEnabled(False)
            self.lbl_status.setText("正在终止，请稍候...")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #f38ba8; }")
            
    def on_analysis_finished(self, result_json):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setStyleSheet("")
        self.progress_bar.setValue(100)
        self.lbl_status.setText("全部完成！")
        
        try:
            data = json.loads(result_json)
            md_text = data.get("report", "")
            skill_dir = data.get("skill_dir")
            
            html = markdown.markdown(md_text)
            self.report_browser.setHtml(REPORT_HTML_STYLE + html)
            self.tabs.setCurrentIndex(0)  # 跳到最终报告
            
            if skill_dir:
                msg = f"分析完成！\n\n报告及 Skill 包已归档至:\n{skill_dir}"
            else:
                msg = "分析完成！(Skill 蒸馏可能出现问题，请查看控制台)"
            QMessageBox.information(self, "完成", msg)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"解析结果失败: {e}")

    def on_analysis_error(self, err_msg):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setStyleSheet("")
        self.lbl_status.setText("任务终止或发生错误")
        QMessageBox.critical(self, "执行失败", err_msg)
        self.report_browser.setHtml(REPORT_HTML_STYLE + f"<h3 style='color:#f38ba8;'>处理失败: {err_msg}</h3>")
