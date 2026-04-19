DARK_THEME_CSS = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
}
QLabel {
    color: #bac2de;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    color: #89b4fa;
    margin-bottom: 10px;
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
}
QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QPushButton {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
    border-radius: 6px;
    padding: 10px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #b4befe;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #a6adc8;
}
QPushButton#btn_export {
    background-color: #a6e3a1;
    color: #11111b;
}
QPushButton#btn_export:hover {
    background-color: #94e2d5;
}
QCheckBox {
    color: #f38ba8;
    font-weight: bold;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #f38ba8;
    border: 1px solid #f38ba8;
}
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #f9e2af;
    border-radius: 6px;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background-color: #11111b;
}
QTabBar::tab {
    background-color: #1e1e2e;
    color: #6c7086;
    padding: 12px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #11111b;
    color: #89b4fa;
    font-weight: bold;
}
QSplitter::handle {
    background-color: #313244;
}
QTextBrowser {
    background-color: #11111b;
    color: #cdd6f4;
    border: none;
    padding: 10px;
}
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
}
QComboBox:focus { border: 1px solid #89b4fa; }
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #89b4fa; }
QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
"""

REPORT_HTML_STYLE = """
<style>
    body { font-family: "Microsoft YaHei", -apple-system, sans-serif; color: #cdd6f4; line-height: 1.8; margin: 20px; font-size: 15px;}
    h1 { color: #cba6f7; border-bottom: 2px solid #585b70; padding-bottom: 8px; margin-top: 20px;}
    h2 { color: #89b4fa; margin-top: 24px; border-left: 4px solid #f38ba8; padding-left: 10px;}
    h3 { color: #a6e3a1; }
    strong { color: #f9e2af; font-weight: 600;}
    ul { margin-top: 5px; padding-left: 20px;}
    li { margin-bottom: 8px; }
    blockquote { background-color: #313244; border-left: 4px solid #a6e3a1; margin: 1.5em 0; padding: 1em; border-radius: 6px; color: #bac2de; font-style: italic;}
    code { background-color: #313244; padding: 2px 6px; border-radius: 4px; color: #f38ba8; font-family: Consolas, monospace;}
</style>
"""
