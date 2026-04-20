"""
设置对话框 - 集中管理所有可配置参数
"""
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import API_PRESETS, EMBEDDING_PROVIDER_PRESETS, FIDELITY_PROVIDER_PRESETS, save_config


EMBEDDING_MODEL_PRESETS = {
    "builtin": ["builtin-hash-384", "builtin-hash-512"],
    "ollama": ["qwen3-embedding:0.6b", "qwen3-embedding:4b", "bge-m3"],
    "remote_openai_compatible": ["text-embedding-3-small", "text-embedding-3-large", "BAAI/bge-m3"],
}

FIDELITY_MODEL_PRESETS = {
    "remote": ["(跟随主模型)"],
    "ollama": ["qwen3:4b", "qwen3.5:4b", "qwen2.5:3b", "qwen2.5:7b"],
}


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("⚙️ 高级设置")
        self.setMinimumWidth(620)
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

        tabs = QTabWidget()
        layout.addWidget(tabs)

        llm_tab = QWidget()
        llm_layout = QVBoxLayout(llm_tab)
        llm_layout.setSpacing(10)

        api_group = QGroupBox("🌐 主 LLM 设置")
        api_form = QFormLayout()

        self.combo_preset = QComboBox()
        for name in API_PRESETS:
            self.combo_preset.addItem(name)
        current_preset = self.config.get("api_preset", "本地 (AIStudioToAPI)")
        idx = self.combo_preset.findText(current_preset)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)
        self.combo_preset.currentTextChanged.connect(self._on_api_preset_changed)
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
        api_form.addRow("温度:", self.spin_temperature)

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
        self.spin_price_in.setValue(self.config.get("price_per_m_input", 0.5))
        api_form.addRow("输入价格:", self.spin_price_in)

        self.spin_price_out = QDoubleSpinBox()
        self.spin_price_out.setRange(0.0, 100.0)
        self.spin_price_out.setDecimals(4)
        self.spin_price_out.setPrefix("$ ")
        self.spin_price_out.setSuffix(" / M tokens")
        self.spin_price_out.setValue(self.config.get("price_per_m_output", 1.5))
        api_form.addRow("输出价格:", self.spin_price_out)

        api_group.setLayout(api_form)
        llm_layout.addWidget(api_group)
        llm_layout.addStretch()
        tabs.addTab(llm_tab, "主 LLM")

        embedding_tab = QWidget()
        embedding_layout = QVBoxLayout(embedding_tab)
        embedding_layout.setSpacing(10)

        embedding_group = QGroupBox("🧠 Embedding / 语义检索")
        embedding_form = QFormLayout()

        self.chk_embedding_enabled = QCheckBox("启用 embedding 与语义检索")
        self.chk_embedding_enabled.setChecked(self.config.get("embedding_enabled", False))
        embedding_form.addRow("启用 embedding:", self.chk_embedding_enabled)

        self.combo_embedding_preset = QComboBox()
        for name in EMBEDDING_PROVIDER_PRESETS:
            self.combo_embedding_preset.addItem(name)
        current_embedding_preset = self.config.get("embedding_preset", "内置 (Builtin)")
        idx = self.combo_embedding_preset.findText(current_embedding_preset)
        if idx >= 0:
            self.combo_embedding_preset.setCurrentIndex(idx)
        self.combo_embedding_preset.currentTextChanged.connect(self._on_embedding_preset_changed)
        embedding_form.addRow("Embedding 预设:", self.combo_embedding_preset)

        self.combo_embedding_provider = QComboBox()
        for provider in ["builtin", "ollama", "remote_openai_compatible"]:
            self.combo_embedding_provider.addItem(provider)
        current_provider = self.config.get("embedding_provider", "builtin")
        idx = self.combo_embedding_provider.findText(current_provider)
        if idx >= 0:
            self.combo_embedding_provider.setCurrentIndex(idx)
        self.combo_embedding_provider.currentTextChanged.connect(self._on_embedding_provider_changed)
        embedding_form.addRow("Provider:", self.combo_embedding_provider)

        self.input_embedding_api_base = QLineEdit(self.config.get("embedding_api_base", ""))
        embedding_form.addRow("Embedding Base URL:", self.input_embedding_api_base)

        self.input_embedding_api_key = QLineEdit(self.config.get("embedding_api_key", ""))
        self.input_embedding_api_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        embedding_form.addRow("Embedding API Key:", self.input_embedding_api_key)

        self.combo_embedding_model = QComboBox()
        self.input_embedding_model = QLineEdit(self.config.get("embedding_model", "builtin-hash-384"))
        self.combo_embedding_model.currentTextChanged.connect(self._on_embedding_model_preset_changed)
        embedding_model_row = QHBoxLayout()
        embedding_model_row.addWidget(self.combo_embedding_model, 2)
        embedding_model_row.addWidget(self.input_embedding_model, 3)
        embedding_form.addRow("Embedding 模型:", embedding_model_row)

        self.spin_builtin_dim = QSpinBox()
        self.spin_builtin_dim.setRange(128, 2048)
        self.spin_builtin_dim.setSingleStep(64)
        self.spin_builtin_dim.setValue(self.config.get("builtin_embedding_dim", 384))
        embedding_form.addRow("内置向量维度:", self.spin_builtin_dim)

        self.spin_embedding_timeout = QSpinBox()
        self.spin_embedding_timeout.setRange(10, 1800)
        self.spin_embedding_timeout.setSuffix(" 秒")
        self.spin_embedding_timeout.setValue(self.config.get("embedding_timeout", 120))
        embedding_form.addRow("Embedding 超时:", self.spin_embedding_timeout)

        self.chk_auto_pull = QCheckBox("Ollama 缺模型时自动拉取")
        self.chk_auto_pull.setChecked(self.config.get("auto_pull_local_models", True))
        embedding_form.addRow("自动拉取:", self.chk_auto_pull)

        self.chk_semantic_retrieval = QCheckBox("启用语义检索")
        self.chk_semantic_retrieval.setChecked(self.config.get("semantic_retrieval_enabled", True))
        embedding_form.addRow("语义检索:", self.chk_semantic_retrieval)

        self.spin_semantic_top_k = QSpinBox()
        self.spin_semantic_top_k.setRange(1, 50)
        self.spin_semantic_top_k.setValue(self.config.get("semantic_retrieval_top_k", 8))
        embedding_form.addRow("语义检索 Top-K:", self.spin_semantic_top_k)

        embedding_group.setLayout(embedding_form)
        embedding_layout.addWidget(embedding_group)
        embedding_layout.addStretch()
        tabs.addTab(embedding_tab, "Embedding")

        fidelity_tab = QWidget()
        fidelity_layout = QVBoxLayout(fidelity_tab)
        fidelity_layout.setSpacing(10)

        fidelity_group = QGroupBox("💬 Fidelity 原话提取")
        fidelity_form = QFormLayout()

        self.combo_fidelity_preset = QComboBox()
        for name in FIDELITY_PROVIDER_PRESETS:
            self.combo_fidelity_preset.addItem(name)
        current_fidelity_preset = self.config.get("fidelity_preset", "本地 Ollama Qwen 4B")
        idx = self.combo_fidelity_preset.findText(current_fidelity_preset)
        if idx >= 0:
            self.combo_fidelity_preset.setCurrentIndex(idx)
        self.combo_fidelity_preset.currentTextChanged.connect(self._on_fidelity_preset_changed)
        fidelity_form.addRow("Fidelity 预设:", self.combo_fidelity_preset)

        self.combo_fidelity_provider = QComboBox()
        for provider in ["remote", "ollama"]:
            self.combo_fidelity_provider.addItem(provider)
        current_fidelity_provider = self.config.get("fidelity_provider", "ollama")
        idx = self.combo_fidelity_provider.findText(current_fidelity_provider)
        if idx >= 0:
            self.combo_fidelity_provider.setCurrentIndex(idx)
        self.combo_fidelity_provider.currentTextChanged.connect(self._on_fidelity_provider_changed)
        fidelity_form.addRow("Provider:", self.combo_fidelity_provider)

        self.input_fidelity_api_base = QLineEdit(self.config.get("fidelity_api_base", "http://localhost:11434"))
        fidelity_form.addRow("Fidelity Base URL:", self.input_fidelity_api_base)

        self.combo_fidelity_model = QComboBox()
        self.input_fidelity_model = QLineEdit(self.config.get("fidelity_model", "qwen3:4b"))
        self.combo_fidelity_model.currentTextChanged.connect(self._on_fidelity_model_preset_changed)
        fidelity_model_row = QHBoxLayout()
        fidelity_model_row.addWidget(self.combo_fidelity_model, 2)
        fidelity_model_row.addWidget(self.input_fidelity_model, 3)
        fidelity_form.addRow("Fidelity 模型:", fidelity_model_row)

        self.spin_fidelity_timeout = QSpinBox()
        self.spin_fidelity_timeout.setRange(30, 1800)
        self.spin_fidelity_timeout.setSuffix(" 秒")
        self.spin_fidelity_timeout.setValue(self.config.get("fidelity_timeout", 180))
        fidelity_form.addRow("Fidelity 超时:", self.spin_fidelity_timeout)

        self.spin_fidelity_temperature = QDoubleSpinBox()
        self.spin_fidelity_temperature.setRange(0.0, 2.0)
        self.spin_fidelity_temperature.setSingleStep(0.1)
        self.spin_fidelity_temperature.setValue(self.config.get("fidelity_temperature", 0.2))
        fidelity_form.addRow("Fidelity 温度:", self.spin_fidelity_temperature)

        self.chk_auto_pull_fidelity = QCheckBox("Fidelity 缺模型时自动拉取")
        self.chk_auto_pull_fidelity.setChecked(self.config.get("auto_pull_fidelity_models", True))
        fidelity_form.addRow("自动拉取:", self.chk_auto_pull_fidelity)

        fidelity_group.setLayout(fidelity_form)
        fidelity_layout.addWidget(fidelity_group)
        fidelity_layout.addStretch()
        tabs.addTab(fidelity_tab, "Fidelity")

        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        data_layout.setSpacing(10)

        data_group = QGroupBox("📊 数据处理")
        data_form = QFormLayout()

        self.spin_context = QSpinBox()
        self.spin_context.setRange(0, 10)
        self.spin_context.setValue(self.config.get("context_window", 2))
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

        self.spin_highlight_candidates = QSpinBox()
        self.spin_highlight_candidates.setRange(20, 2000)
        self.spin_highlight_candidates.setValue(self.config.get("highlight_candidate_limit", 300))
        data_form.addRow("候选池上限:", self.spin_highlight_candidates)

        self.spin_highlight_output = QSpinBox()
        self.spin_highlight_output.setRange(10, 500)
        self.spin_highlight_output.setValue(self.config.get("highlight_output_limit", 50))
        data_form.addRow("高价值原话输出上限:", self.spin_highlight_output)

        self.spin_fidelity_candidate_min = QSpinBox()
        self.spin_fidelity_candidate_min.setRange(0, 200)
        self.spin_fidelity_candidate_min.setValue(self.config.get("fidelity_candidate_min", 30))
        data_form.addRow("Fidelity 最低候选数:", self.spin_fidelity_candidate_min)

        self.spin_fidelity_candidate_max = QSpinBox()
        self.spin_fidelity_candidate_max.setRange(1, 300)
        self.spin_fidelity_candidate_max.setValue(self.config.get("fidelity_candidate_max", 50))
        data_form.addRow("Fidelity 最高候选数:", self.spin_fidelity_candidate_max)

        data_group.setLayout(data_form)
        data_layout.addWidget(data_group)
        data_layout.addStretch()
        tabs.addTab(data_tab, "数据处理")

        perf_tab = QWidget()
        perf_layout = QVBoxLayout(perf_tab)
        perf_layout.setSpacing(10)

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
        perf_layout.addWidget(perf_group)
        perf_layout.addStretch()
        tabs.addTab(perf_tab, "并发与限流")

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 保存并关闭")
        btn_save.clicked.connect(self.accept_and_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self._refresh_embedding_model_presets()
        self._refresh_fidelity_model_presets()
        self._apply_provider_visibility()

    def _on_api_preset_changed(self, name):
        url = API_PRESETS.get(name, "")
        if name != "自定义" and url:
            self.input_api_base.setText(url)

    def _on_embedding_preset_changed(self, name):
        preset = EMBEDDING_PROVIDER_PRESETS.get(name, {})
        provider = preset.get("embedding_provider", "builtin")
        self.combo_embedding_provider.setCurrentText(provider)
        self.input_embedding_api_base.setText(preset.get("embedding_api_base", ""))
        self.input_embedding_model.setText(preset.get("embedding_model", ""))
        self._refresh_embedding_model_presets()
        self._apply_provider_visibility()

    def _on_embedding_provider_changed(self, _name):
        self._refresh_embedding_model_presets()
        self._apply_provider_visibility()

    def _refresh_embedding_model_presets(self):
        provider = self.combo_embedding_provider.currentText()
        current_text = self.input_embedding_model.text().strip()
        self.combo_embedding_model.blockSignals(True)
        self.combo_embedding_model.clear()
        for model_name in EMBEDDING_MODEL_PRESETS.get(provider, []):
            self.combo_embedding_model.addItem(model_name)
        if current_text:
            idx = self.combo_embedding_model.findText(current_text)
            if idx >= 0:
                self.combo_embedding_model.setCurrentIndex(idx)
        self.combo_embedding_model.blockSignals(False)

    def _on_embedding_model_preset_changed(self, name):
        if name:
            self.input_embedding_model.setText(name)

    def _apply_provider_visibility(self):
        provider = self.combo_embedding_provider.currentText()
        is_builtin = provider == "builtin"
        is_ollama = provider == "ollama"
        is_remote = provider == "remote_openai_compatible"

        self.input_embedding_api_base.setEnabled(is_ollama or is_remote)
        self.input_embedding_api_key.setEnabled(is_remote)
        self.chk_auto_pull.setEnabled(is_ollama)
        self.spin_builtin_dim.setEnabled(is_builtin)
        fidelity_provider = self.combo_fidelity_provider.currentText()
        self.input_fidelity_api_base.setEnabled(fidelity_provider == "ollama")
        self.chk_auto_pull_fidelity.setEnabled(fidelity_provider == "ollama")

    def _on_fidelity_preset_changed(self, name):
        preset = FIDELITY_PROVIDER_PRESETS.get(name, {})
        provider = preset.get("fidelity_provider", "remote")
        self.combo_fidelity_provider.setCurrentText(provider)
        self.input_fidelity_api_base.setText(preset.get("fidelity_api_base", ""))
        self.input_fidelity_model.setText(preset.get("fidelity_model", ""))
        self._refresh_fidelity_model_presets()
        self._apply_provider_visibility()

    def _on_fidelity_provider_changed(self, _name):
        self._refresh_fidelity_model_presets()
        self._apply_provider_visibility()

    def _refresh_fidelity_model_presets(self):
        provider = self.combo_fidelity_provider.currentText()
        current_text = self.input_fidelity_model.text().strip()
        self.combo_fidelity_model.blockSignals(True)
        self.combo_fidelity_model.clear()
        for model_name in FIDELITY_MODEL_PRESETS.get(provider, []):
            self.combo_fidelity_model.addItem(model_name)
        if current_text:
            idx = self.combo_fidelity_model.findText(current_text)
            if idx >= 0:
                self.combo_fidelity_model.setCurrentIndex(idx)
        self.combo_fidelity_model.blockSignals(False)

    def _on_fidelity_model_preset_changed(self, name):
        if name and name != "(跟随主模型)":
            self.input_fidelity_model.setText(name)

    def accept_and_save(self):
        self.config["api_preset"] = self.combo_preset.currentText()
        self.config["api_base"] = self.input_api_base.text().strip()
        self.config["api_key"] = self.input_api_key.text().strip()
        self.config["model"] = self.input_model.text().strip()
        self.config["temperature"] = self.spin_temperature.value()
        self.config["max_tokens"] = self.spin_max_tokens.value()
        self.config["request_timeout"] = self.spin_timeout.value()
        self.config["max_retries"] = self.spin_retries.value()
        self.config["price_per_m_input"] = self.spin_price_in.value()
        self.config["price_per_m_output"] = self.spin_price_out.value()

        self.config["embedding_enabled"] = self.chk_embedding_enabled.isChecked()
        self.config["embedding_preset"] = self.combo_embedding_preset.currentText()
        self.config["embedding_provider"] = self.combo_embedding_provider.currentText()
        self.config["embedding_api_base"] = self.input_embedding_api_base.text().strip()
        self.config["embedding_api_key"] = self.input_embedding_api_key.text().strip()
        self.config["embedding_model"] = self.input_embedding_model.text().strip()
        self.config["builtin_embedding_dim"] = self.spin_builtin_dim.value()
        self.config["embedding_timeout"] = self.spin_embedding_timeout.value()
        self.config["auto_pull_local_models"] = self.chk_auto_pull.isChecked()
        self.config["semantic_retrieval_enabled"] = self.chk_semantic_retrieval.isChecked()
        self.config["semantic_retrieval_top_k"] = self.spin_semantic_top_k.value()
        self.config["fidelity_preset"] = self.combo_fidelity_preset.currentText()
        self.config["fidelity_provider"] = self.combo_fidelity_provider.currentText()
        self.config["fidelity_api_base"] = self.input_fidelity_api_base.text().strip()
        self.config["fidelity_model"] = self.input_fidelity_model.text().strip()
        self.config["fidelity_timeout"] = self.spin_fidelity_timeout.value()
        self.config["fidelity_temperature"] = self.spin_fidelity_temperature.value()
        self.config["auto_pull_fidelity_models"] = self.chk_auto_pull_fidelity.isChecked()

        self.config["context_window"] = self.spin_context.value()
        self.config["chunk_size"] = self.spin_chunk.value()
        self.config["sample_limit"] = self.spin_sample.value()
        self.config["agent_mode"] = self.chk_agent.isChecked()
        self.config["highlight_candidate_limit"] = self.spin_highlight_candidates.value()
        self.config["highlight_output_limit"] = self.spin_highlight_output.value()
        self.config["fidelity_candidate_min"] = self.spin_fidelity_candidate_min.value()
        self.config["fidelity_candidate_max"] = self.spin_fidelity_candidate_max.value()

        self.config["map_workers"] = self.spin_map_workers.value()
        self.config["reduce_workers"] = self.spin_reduce_workers.value()
        self.config["skill_workers"] = self.spin_skill_workers.value()
        self.config["rate_limit_calls"] = self.spin_rate_calls.value()
        self.config["rate_limit_period"] = self.spin_rate_period.value()

        save_config(self.config)
        self.accept()

    def get_config(self):
        return self.config
