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

PRODUCT_SHELL = """
QWidget#AppShell, QWidget#MainColumn { background: #f3f6fa; }
QFrame#NavigationRail { background: #101b2e; border: none; }
QLabel#NavBrand { color: #f2c94c; border: 2px solid #f2c94c; border-radius: 20px; font-size: 13px; font-weight: 800; }
QLabel#NavCaption { color: #71839c; font-size: 10px; font-weight: 700; }
QPushButton#NavItem { min-width: 62px; min-height: 58px; padding: 5px 4px; background: transparent; border: none; border-left: 3px solid transparent; border-radius: 0; color: #aebbd0; font-size: 12px; font-weight: 650; }
QPushButton#NavItem:hover { background: #162944; color: white; }
QPushButton#NavItem:checked { background: #193b68; border-left-color: #4d91ff; color: white; }
QFrame#TopBar { background: white; border: none; border-bottom: 1px solid #d9e0ea; }
QLabel#TopEyebrow { color: #7d8999; font-size: 10px; font-weight: 700; }
QLabel#TopTitle { color: #172235; font-size: 21px; font-weight: 750; }
QPushButton#StatusPill { min-height: 32px; padding: 5px 12px; background: #edf8f5; border: 1px solid #d2ebe4; border-radius: 16px; color: #227d6a; }
QPushButton#IconButton { min-width: 34px; min-height: 34px; max-width: 34px; padding: 0; background: #f8fafc; border: 1px solid #d9e0ea; border-radius: 8px; font-size: 16px; }
QFrame#SessionBar { background: transparent; border: none; }
QFrame#Sidebar, QFrame#Workspace { border: 1px solid #d9e0ea; border-radius: 12px; }
QFrame#Workspace { border-top: 3px solid #4d91ff; }
QFrame#Sidebar { border-top: 3px solid #f2c94c; }
QWidget#TabPage, QWidget#MoveDetailsBody, QWidget#MoveDescription, QWidget#DialogViewport, QWidget#DialogPage { background: white; }
QLabel#SectionKicker { color: #4d91ff; font-size: 10px; font-weight: 800; }
QLabel#StatusMessage { border-left: 3px solid #4d91ff; }
QDialog QFrame#SettingsCard { background: white; border: 1px solid #d9e0ea; border-radius: 12px; }
QLabel#SettingsTitle { color: #172235; font-size: 22px; font-weight: 750; }
QLabel#SettingsSection { color: #172235; font-size: 15px; font-weight: 700; }
QPushButton#DangerGhost { color: #b33f58; background: #fff5f7; border-color: #f0ced6; }
"""

DARK_OVERRIDES = """
QWidget { color: #dbe4f0; }
QMainWindow, QDialog, QWidget#AppShell, QWidget#MainColumn { background: #0c1525; }
QFrame#TopBar { background: #111d31; border-bottom-color: #27364d; }
QLabel#TopEyebrow, QLabel#Muted, QLabel#HeaderNote { color: #8392a8; }
QLabel#TopTitle, QLabel#PokemonName, QLabel#MoveTitle, QLabel#SettingsTitle, QLabel#SettingsSection, QLabel#SectionTitle { color: #f2f6fb; }
QFrame#Sidebar, QFrame#Workspace, QDialog QFrame#SettingsCard { background: #111d31; border-color: #27364d; }
QFrame#DropPreview, QFrame#MoveDetails { background: #15243a; border-color: #34465f; }
QLabel#DropHint, QLabel#Effect { color: #b8c5d6; }
QPushButton { background: #18283f; border-color: #34465f; color: #dbe4f0; }
QPushButton:hover { background: #203653; border-color: #4d91ff; }
QPushButton:pressed { background: #294363; }
QPushButton:disabled { color: #69778b; background: #131f31; border-color: #26354a; }
QPushButton#Navigation { background: #15243a; }
QPushButton#Primary { background: #397fde; border-color: #397fde; }
QPushButton#Primary:hover { background: #4d91ff; }
QPushButton#IconButton { background: #15243a; border-color: #34465f; color: #dbe4f0; }
QPushButton#StatusPill { background: #15372f; border-color: #245e50; color: #69d6b8; }
QLineEdit, QComboBox, QSpinBox, QTextEdit { background: #101b2e; border-color: #34465f; color: #e6edf6; selection-background-color: #397fde; }
QComboBox QAbstractItemView { background: #15243a; color: #e6edf6; selection-background-color: #274d79; }
QListWidget { background: transparent; color: #dbe4f0; }
QListWidget::item { background: #15243a; border-color: #27364d; }
QListWidget::item:selected { background: #1d3b61; border-color: #4d91ff; color: white; }
QTableWidget { background: #111d31; alternate-background-color: #142238; border-color: #27364d; gridline-color: #27364d; color: #dbe4f0; selection-background-color: #274d79; selection-color: white; }
QHeaderView::section { background: #17263d; color: #9fb0c5; border-bottom-color: #34465f; }
QTabBar::tab { background: #142238; color: #9fb0c5; border-color: #27364d; }
QTabBar::tab:selected { background: #1a2d48; color: #78adff; border-bottom-color: #4d91ff; }
QTabWidget::pane { background: #111d31; border-color: #27364d; }
QWidget#TabPage, QWidget#MoveDetailsBody, QWidget#MoveDescription, QWidget#DialogViewport, QWidget#DialogPage { background: #111d31; }
QFrame#MoveDetails QWidget#MoveDetailsBody, QFrame#MoveDetails QWidget#MoveDescription { background: #15243a; }
QLabel#StatusMessage { color: #bcd1e6; background: #14253b; }
QProgressBar { background: #17263d; }
QProgressBar::chunk { background: #4d91ff; }
QScrollBar:vertical { background: #101b2e; }
QScrollBar::handle:vertical { background: #40516a; }
QToolTip { background: #17263d; color: white; border-color: #40516a; }
"""


BASE_STYLE = STYLE + PRODUCT_SHELL


def style_for(dark=False):
    """Return the complete application stylesheet for the selected theme."""
    return BASE_STYLE + (DARK_OVERRIDES if dark else "")


# Backwards-compatible light theme used by dialogs importing STYLE directly.
STYLE = BASE_STYLE
