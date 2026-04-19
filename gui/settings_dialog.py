"""
设置对话框 - 集中管理所有可配置参数
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
                             QPushButton, QGroupBox, QFormLayout, QMessageBox, QCheckBox)
from PyQt5.QtCore import Qt
from core.config import API_PRESETS, load_config, save_config


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("⚙️ 高级设置")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; color: #89b4fa; 
                border: 1px solid #45475a; border-radius: 8px; 
                margin-top: 12px; padding-top: 18px;
            }
            QGroupBox::title { subcontrol-position: top left; padding: 4px 8px; }
        """)
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # === API 设置 ===
        api_group = QGroupBox("🌐 API 设置")
        api_form = QFormLayout()
        
        self.combo_preset = QComboBox()
        for name in API_PRESETS:
            self.combo_preset.addItem(name)
        current_preset = self.config.get("api_preset", "本地 (AIStudioToAPI)")
        idx = self.combo_preset.findText(current_preset)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)
        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        api_form.addRow("API 镜像站:", self.combo_preset)
        
        self.input_api_base = QLineEdit(self.config.get("api_base", ""))
        api_form.addRow("Base URL:", self.input_api_base)
        
        self.input_api_key = QLineEdit(self.config.get("api_key", ""))
        self.input_api_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        api_form.addRow("API Key:", self.input_api_key)
        
        self.input_model = QLineEdit(self.config.get("model", "gemini-3-flash-preview"))
        api_form.addRow("模型名称:", self.input_model)
        
        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.1)
        self.spin_temperature.setValue(self.config.get("temperature", 0.2))
        api_form.addRow("温度 (Temperature):", self.spin_temperature)
        
        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(1024, 65536)
        self.spin_max_tokens.setSingleStep(1024)
        self.spin_max_tokens.setValue(self.config.get("max_tokens", 8192))
        api_form.addRow("最大输出 Token:", self.spin_max_tokens)
        
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(30, 1200)
        self.spin_timeout.setSuffix(" 秒")
        self.spin_timeout.setValue(self.config.get("request_timeout", 300))
        api_form.addRow("请求超时:", self.spin_timeout)
        
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1, 10)
        self.spin_retries.setValue(self.config.get("max_retries", 3))
        api_form.addRow("失败重试次数:", self.spin_retries)

        self.spin_price_in = QDoubleSpinBox()
        self.spin_price_in.setRange(0.0, 100.0)
        self.spin_price_in.setDecimals(4)
        self.spin_price_in.setPrefix("$ ")
        self.spin_price_in.setSuffix(" / M tokens")
        self.spin_price_in.setValue(self.config.get("price_per_m_input", 0.95))
        api_form.addRow("输入价格 (Input):", self.spin_price_in)

        self.spin_price_out = QDoubleSpinBox()
        self.spin_price_out.setRange(0.0, 100.0)
        self.spin_price_out.setDecimals(4)
        self.spin_price_out.setPrefix("$ ")
        self.spin_price_out.setSuffix(" / M tokens")
        self.spin_price_out.setValue(self.config.get("price_per_m_output", 3.15))
        api_form.addRow("输出价格 (Output):", self.spin_price_out)
        
        api_group.setLayout(api_form)
        layout.addWidget(api_group)
        
        # === 数据处理 ===
        data_group = QGroupBox("📊 数据处理")
        data_form = QFormLayout()
        
        self.spin_context = QSpinBox()
        self.spin_context.setRange(0, 10)
        self.spin_context.setValue(self.config.get("context_window", 2))
        self.spin_context.setToolTip("目标人物每条发言上下各截取N条消息作为上下文")
        data_form.addRow("上下文窗口 (±N条):", self.spin_context)
        
        self.spin_chunk = QSpinBox()
        self.spin_chunk.setRange(10000, 500000)
        self.spin_chunk.setSingleStep(10000)
        self.spin_chunk.setValue(self.config.get("chunk_size", 100000))
        self.spin_chunk.setSuffix(" 字符")
        data_form.addRow("分段最大字符数:", self.spin_chunk)
        
        self.spin_sample = QSpinBox()
        self.spin_sample.setRange(100, 50000)
        self.spin_sample.setSingleStep(500)
        self.spin_sample.setValue(self.config.get("sample_limit", 5000))
        data_form.addRow("抽样目标条数:", self.spin_sample)

        self.chk_agent = QCheckBox("开启 Agent 深度审计模式")
        self.chk_agent.setChecked(self.config.get("agent_mode", False))
        data_form.addRow("Agent 模式:", self.chk_agent)
        
        data_group.setLayout(data_form)
        layout.addWidget(data_group)
        
        # === 并发控制 ===
        perf_group = QGroupBox("⚡ 并发与限流")
        perf_form = QFormLayout()
        
        self.spin_map_workers = QSpinBox()
        self.spin_map_workers.setRange(1, 20)
        self.spin_map_workers.setValue(self.config.get("map_workers", 5))
        perf_form.addRow("Map 并发数:", self.spin_map_workers)
        
        self.spin_reduce_workers = QSpinBox()
        self.spin_reduce_workers.setRange(1, 10)
        self.spin_reduce_workers.setValue(self.config.get("reduce_workers", 4))
        perf_form.addRow("Reduce 并发数:", self.spin_reduce_workers)
        
        self.spin_skill_workers = QSpinBox()
        self.spin_skill_workers.setRange(1, 12)
        self.spin_skill_workers.setValue(self.config.get("skill_workers", 6))
        perf_form.addRow("Skill 蒸馏并发数:", self.spin_skill_workers)
        
        self.spin_rate_calls = QSpinBox()
        self.spin_rate_calls.setRange(1, 100)
        self.spin_rate_calls.setValue(self.config.get("rate_limit_calls", 14))
        perf_form.addRow("每分钟最大调用:", self.spin_rate_calls)
        
        self.spin_rate_period = QSpinBox()
        self.spin_rate_period.setRange(10, 300)
        self.spin_rate_period.setSuffix(" 秒")
        self.spin_rate_period.setValue(self.config.get("rate_limit_period", 60))
        perf_form.addRow("限流周期:", self.spin_rate_period)
        
        perf_group.setLayout(perf_form)
        layout.addWidget(perf_group)
        
        # === 按钮 ===
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 保存并关闭")
        btn_save.clicked.connect(self.accept_and_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
    
    def _on_preset_changed(self, name):
        url = API_PRESETS.get(name, "")
        if name != "自定义" and url:
            self.input_api_base.setText(url)
    
    def accept_and_save(self):
        self.config["api_preset"] = self.combo_preset.currentText()
        self.config["api_base"] = self.input_api_base.text().strip()
        self.config["api_key"] = self.input_api_key.text().strip()
        self.config["model"] = self.input_model.text().strip()
        self.config["temperature"] = self.spin_temperature.value()
        self.config["max_tokens"] = self.spin_max_tokens.value()
        self.config["request_timeout"] = self.spin_timeout.value()
        self.config["max_retries"] = self.spin_retries.value()
        self.config["context_window"] = self.spin_context.value()
        self.config["chunk_size"] = self.spin_chunk.value()
        self.config["sample_limit"] = self.spin_sample.value()
        self.config["agent_mode"] = self.chk_agent.isChecked()
        self.config["map_workers"] = self.spin_map_workers.value()
        self.config["reduce_workers"] = self.spin_reduce_workers.value()
        self.config["skill_workers"] = self.spin_skill_workers.value()
        self.config["rate_limit_calls"] = self.spin_rate_calls.value()
        self.config["rate_limit_period"] = self.spin_rate_period.value()
        self.config["price_per_m_input"] = self.spin_price_in.value()
        self.config["price_per_m_output"] = self.spin_price_out.value()
        
        save_config(self.config)
        self.accept()
    
    def get_config(self):
        return self.config
