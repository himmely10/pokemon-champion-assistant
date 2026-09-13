"""Shared desktop colors, typography, focus states and readable controls."""
STYLE = """
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #26374a; }
QMainWindow { background: #eef2f5; }
QFrame#Header { background: #172b3d; border-radius: 12px; }
QLabel#Brand { color: white; font-size: 24px; font-weight: 700; }
QLabel#HeaderNote { color: #b8cbd5; font-size: 12px; }
QLabel#ModeBadge { background: #29475b; color: #93e0c7; border-radius: 11px; padding: 7px 16px; font-weight: 600; }
QFrame#Sidebar, QFrame#Workspace { background: white; border-radius: 12px; }
QLabel#SectionTitle { color: #253c4e; font-size: 15px; font-weight: 700; }
QLabel#Muted { color: #718091; font-size: 12px; }
QLabel#PokemonName { font-size: 27px; font-weight: 700; color: #172b3d; }
QLabel#DropHint { color: #788896; font-size: 14px; }
QFrame#DropPreview { border: 1px dashed #adc2cd; border-radius: 10px; background: #f6f9fb; }
QPushButton { background: #edf3f6; border: 1px solid #d8e2e7; border-radius: 7px; padding: 8px 13px; font-weight: 600; }
QPushButton:hover { background: #dfeef0; border-color: #96bebc; }
QPushButton:pressed { background: #cee5df; }
QPushButton:disabled { color: #a7b2bd; background: #f4f6f8; border-color: #e7ebef; }
QPushButton#Primary { background: #147e6e; border: 1px solid #147e6e; color: white; }
QPushButton#Primary:hover { background: #096b5d; }
QPushButton#Primary:disabled { background: #a0bdb6; border-color: #a0bdb6; }
QPushButton#Cancel { color: #a34b4f; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #d6e0e6; border-radius: 6px; padding: 7px; min-height: 21px; }
QLineEdit:focus, QComboBox:focus { border-color: #147e6e; }
QListWidget { border: none; background: transparent; outline: none; }
QListWidget::item { border: 1px solid #e6ecf0; border-radius: 8px; padding: 6px; margin-bottom: 5px; background: #fbfcfd; }
QListWidget::item:selected { background: #e2f3ed; border-color: #76b5a2; color: #154d40; }
QTableWidget { border: 1px solid #e4eaee; border-radius: 6px; gridline-color: #edf1f4; background: white; selection-background-color: #ddf1e9; selection-color: #173c30; outline: none; }
QTableWidget::item { padding-left: 9px; padding-right: 9px; }
QHeaderView::section { background: #f0f5f7; color: #617482; border: none; border-bottom: 1px solid #dce5eb; padding: 8px; font-size: 12px; font-weight: 600; }
QGroupBox { border: none; margin-top: 23px; font-size: 14px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 2px; }
QFrame#MoveDetails { background: #f5f8fa; border: 1px solid #e0e8ed; border-radius: 10px; }
QLabel#MoveTitle { font-size: 22px; font-weight: 700; color: #1c3545; }
QLabel#MetricValue { font-family: 'Consolas'; font-size: 21px; font-weight: 600; color: #234d4b; min-height: 28px; }
QLabel#Effect { color: #354c5d; font-size: 14px; line-height: 1.6; }
QToolTip { background: #193446; color: #f0f8fa; border: 1px solid #29475b; padding: 10px; }
QProgressBar { border: none; background: #edf2f5; border-radius: 2px; }
QProgressBar::chunk { background: #36a48b; }
QScrollArea { border: none; background: transparent; }
QSplitter::handle { background: transparent; width: 8px; }
"""

STYLE += """
QWidget { font-size: 14px; }
QMainWindow, QDialog { background: #eef3f6; }
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 2px solid #087f75; }
QPushButton#Navigation { background: white; padding: 9px 18px; }
QPushButton#Primary { background: #087f75; border-color: #087f75; }
QTabBar::tab { background: #e7eef3; color: #415c70; border: 1px solid #d7e2e9; padding: 9px 16px; margin-right: 3px; }
QTabBar::tab:selected { background: white; color: #086d63; border-bottom: 2px solid #087f75; }
QLabel#Muted { color: #587185; }
QLabel#StatusMessage { color: #234e63; background: #e2edf3; border-radius: 7px; padding: 8px 12px; }
QFrame#OnboardingCard { background: white; border: 1px solid #dce6ed; border-radius: 12px; }
QLabel#OnboardingTitle { font-size: 26px; font-weight: 700; color: #183a4b; }
QLabel#OnboardingBody { color: #3d5668; font-size: 15px; }
QScrollBar:vertical { background: #edf3f7; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #b3c5d0; border-radius: 5px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
