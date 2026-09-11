"""Desktop opponent reference workspace. GUI state stays on the Qt main thread."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from PySide6.QtCore import Qt, QThread, Signal, Slot, QUrl, QSize
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QCompleter, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QSizePolicy, QTabWidget)

from ..data.moves import CATEGORIES, TARGETS, accuracy_label, move_tooltip, power_label
from ..data.references import ReferenceCatalog
from ..data.storage import TYPE_NAMES, read_json, save_json
from .obs_dialog import ObsDialog
from .widgets import DropPreview, PanelScrollArea, TYPE_COLORS, label, type_badge
from .worker import AnalysisWorker
from .matchups import MatchupLabel
from ..speed import SPEED_TIERS, speed_lines

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = ROOT / "config/local_ui.json"

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


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()


class MainWindow(QMainWindow):
    requested = Signal(int, str, object)

    def __init__(self, data_dir=ROOT / "pokemon", layout_path=None, settings_path=SETTINGS_PATH, worker_factory=AnalysisWorker, report_path=None):
        super().__init__()
        self.setWindowTitle("Pokemon Champion Assistant · 对战资料台")
        self.resize(1480, 980)
        self.setMinimumSize(1100, 790)
        self.setStyleSheet(STYLE)
        self.catalog = ReferenceCatalog(data_dir)
        self.data_dir, self.layout_path = Path(data_dir), layout_path
        self.settings_path = Path(settings_path)
        self.report_path = Path(report_path) if report_path else None
        self.obs_settings = {"host": "localhost", "port": 4455, "password": "", "source": ""}
        if self.settings_path.exists():
            try:
                saved = read_json(self.settings_path)
                self.obs_settings.update({k: saved[k] for k in ("host", "port", "source") if k in saved})
            except (OSError, ValueError):
                pass
        self.busy = False
        self.revision = 0
        self.closing = False
        self.obs_dialog = None
        self.team_dialog = None
        self.damage_dialog = None
        self.opponents = []
        self.selected_record = None
        self.current_move = None
        self.last_result = None
        self.family = []
        self._build_ui()
        self.thread = QThread(self)
        self.worker = worker_factory(self.catalog.root, layout_path)
        self.worker.moveToThread(self.thread)
        self.requested.connect(self.worker.run)
        self.worker.finished.connect(self._finished)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()
        self._empty_team()
        self._show_empty_reference()

    def _build_ui(self):
        body = QWidget()
        self.setCentralWidget(body)
        page = QVBoxLayout(body)
        page.setContentsMargins(20, 16, 20, 16)
        page.setSpacing(14)
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 10, 22, 10)
        headings = QVBoxLayout()
        headings.addWidget(label("对战资料台", "Brand"))
        subtitle = label("POKÉMON CHAMPION ASSISTANT  /  识别 · 查阅 · 对照", "HeaderNote")
        subtitle.setWordWrap(False)
        headings.addWidget(subtitle)
        header_layout.addLayout(headings)
        header_layout.addStretch()
        self.own_team_button = QPushButton("我方队伍配置")
        self.own_team_button.clicked.connect(self.open_team_editor)
        header_layout.addWidget(self.own_team_button)
        damage_button = QPushButton('双向伤害计算')
        damage_button.clicked.connect(self.open_damage)
        header_layout.addWidget(damage_button)
        header_layout.addWidget(label("双打 · 选队界面", "ModeBadge"))
        page.addWidget(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        page.addWidget(self.splitter, 1)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setMinimumWidth(295)
        side.setMaximumWidth(390)
        left = QVBoxLayout(side)
        left.setContentsMargins(17, 17, 17, 16)
        left.setSpacing(9)
        left.addWidget(label("01  采集游戏画面", "SectionTitle"))
        self.preview = DropPreview()
        self.preview.fileDropped.connect(self.open_image)
        self.preview.openRequested.connect(self.choose_image)
        self.preview.rejected.connect(self.set_status)
        left.addWidget(self.preview)
        self.input_label = label("完整 16:9 选队截图 · 识别右侧六个位置", "Muted")
        left.addWidget(self.input_label)
        buttons = QHBoxLayout()
        self.open_button = QPushButton("打开截图")
        self.open_button.setObjectName("Primary")
        self.open_button.clicked.connect(self.choose_image)
        self.obs_button = QPushButton("连接 OBS")
        self.obs_button.clicked.connect(self.configure_obs)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.obs_button)
        left.addLayout(buttons)
        self.capture_button = QPushButton("从 OBS 截图并识别")
        self.capture_button.clicked.connect(self.capture_obs)
        self.capture_button.setEnabled(bool(self.obs_settings["source"]))
        left.addWidget(self.capture_button)
        self.obs_label = label("OBS 尚未验证连接", "Muted")
        left.addWidget(self.obs_label)
        left.addSpacing(7)
        left.addWidget(label("02  对手队伍", "SectionTitle"))
        self.team_list = QListWidget()
        self.team_list.setIconSize(QSize(36, 36))
        self.team_list.setMinimumHeight(300)
        self.team_list.currentRowChanged.connect(self.select_slot)
        left.addWidget(self.team_list, 1)
        left.addWidget(label("手动查阅 / 修正当前槽位", "Muted"))
        self.pokemon_search = QComboBox()
        self.pokemon_search.setEditable(True)
        self.pokemon_search.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for name, record in self.catalog.search_records():
            self.pokemon_search.addItem(name, record.get("record_id", record["directory"]))
        self.pokemon_search.setCurrentIndex(-1)
        self.pokemon_search.lineEdit().setPlaceholderText("输入宝可梦名字…")
        completer = self.pokemon_search.completer()
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        left.addWidget(self.pokemon_search)
        lookup_actions = QHBoxLayout()
        self.lookup_button = QPushButton("查看资料")
        self.lookup_button.clicked.connect(self.lookup_pokemon)
        self.correct_button = QPushButton("修正槽位")
        self.correct_button.clicked.connect(self.correct_slot)
        lookup_actions.addWidget(self.lookup_button)
        lookup_actions.addWidget(self.correct_button)
        left.addLayout(lookup_actions)
        side.setMinimumHeight(780)
        side.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        side_scroll = PanelScrollArea()
        side_scroll.setMinimumWidth(310)
        side_scroll.setMaximumWidth(410)
        side_scroll.setWidget(side)
        self.splitter.addWidget(side_scroll)

        workspace = QFrame()
        workspace.setObjectName("Workspace")
        center = QVBoxLayout(workspace)
        center.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        center.setContentsMargins(22, 18, 22, 18)
        center.setSpacing(10)
        hero = QHBoxLayout()
        self.hero_icon = QLabel()
        self.hero_icon.setFixedSize(72, 72)
        hero.addWidget(self.hero_icon)
        hero_text = QVBoxLayout()
        self.context_label = label("03  宝可梦资料", "Muted")
        self.pokemon_name = label("选择对手，查看资料", "PokemonName")
        hero_text.addWidget(self.context_label)
        hero_text.addWidget(self.pokemon_name)
        self.types_layout = QHBoxLayout()
        self.types_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        hero_text.addLayout(self.types_layout)
        hero.addLayout(hero_text, 1)
        self.source_note = label("离线资料\n" + self.catalog.index.get("generated_at", "时间未知")[:10], "Muted")
        self.source_note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hero.addWidget(self.source_note)
        center.addLayout(hero)
        self.matchups = MatchupLabel()
        center.addWidget(self.matchups)
        self.reference_tabs = QTabWidget()
        self.reference_tabs.setFixedHeight(300)
        self.stats_table = QTableWidget()
        self.stats_table.setObjectName("StatsTable")
        self.stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.stats_table.verticalHeader().hide()
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.horizontalHeader().setSectionsClickable(True)
        self.stats_table.horizontalHeader().sectionClicked.connect(self.select_form_column)
        self.reference_tabs.addTab(self.stats_table, "种族值对照")
        speed_page = QWidget()
        speed_layout = QVBoxLayout(speed_page)
        speed_layout.setContentsMargins(0, 5, 0, 0)
        speed_controls = QHBoxLayout()
        speed_controls.addWidget(label("加入速度对比", "Muted"))
        self.speed_compare = QComboBox()
        self.speed_compare.setEditable(True)
        self.speed_compare.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.speed_compare.addItem("不添加对比")
        for name, _ in self.catalog.search_records():
            self.speed_compare.addItem(name)
        self.speed_compare.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.speed_compare.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.speed_compare.currentTextChanged.connect(self._render_speed)
        speed_controls.addWidget(self.speed_compare, 1)
        speed_layout.addLayout(speed_controls)
        self.speed_table = QTableWidget()
        self.speed_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.speed_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.speed_table.verticalHeader().hide()
        self.speed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        speed_layout.addWidget(self.speed_table)
        self.reference_tabs.addTab(speed_page, "速度线 · 50级")
        self.reference_tabs.setCurrentIndex(1)
        self.reference_tabs.currentChanged.connect(self._reference_note)
        center.addWidget(self.reference_tabs)
        self.form_note = label("普通形态与各 Mega 分支并排展示；点击列标题切换资料预览。", "Muted")
        center.addWidget(self.form_note)

        move_heading = QHBoxLayout()
        move_heading.addWidget(label("招式资料", "SectionTitle"))
        move_heading.addStretch()
        self.reload_usage_button = QPushButton("载入最新采用率")
        self.reload_usage_button.clicked.connect(self.reload_usage)
        move_heading.addWidget(self.reload_usage_button)
        self.move_search = QLineEdit()
        self.move_search.setPlaceholderText("搜索招式名称、属性或效果…")
        self.move_search.setMaximumWidth(340)
        self.move_search.textChanged.connect(self.filter_moves)
        move_heading.addWidget(self.move_search)
        center.addLayout(move_heading)
        self.moves_splitter = QSplitter(Qt.Orientation.Horizontal)
        tables = QWidget()
        tables_layout = QVBoxLayout(tables)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(5)
        self.damage_group, self.damage_table = self._move_group("伤害招式")
        self.status_group, self.status_table = self._move_group("变化招式")
        tables_layout.addWidget(self.damage_group, 3)
        tables_layout.addWidget(self.status_group, 2)
        self.moves_splitter.addWidget(tables)
        self.details = QFrame()
        self.details.setObjectName("MoveDetails")
        self.details.setMinimumWidth(245)
        details_outer = QVBoxLayout(self.details)
        details_outer.setContentsMargins(0, 0, 0, 0)
        details_viewport = QScrollArea()
        details_viewport.setWidgetResizable(True)
        details_body = QWidget()
        details_body.setMinimumHeight(420)
        details_viewport.setWidget(details_body)
        details_outer.addWidget(details_viewport)
        details_layout = QVBoxLayout(details_body)
        details_layout.setContentsMargins(16, 15, 16, 15)
        details_layout.setSpacing(10)
        details_layout.addWidget(label("招式详情", "Muted"))
        self.move_title = label("点击任意招式", "MoveTitle")
        details_layout.addWidget(self.move_title)
        self.move_tags = QHBoxLayout()
        self.move_tags.setAlignment(Qt.AlignmentFlag.AlignLeft)
        details_layout.addLayout(self.move_tags)
        metrics = QGridLayout()
        self.metric_values = {}
        for i, text in enumerate(("威力", "命中率", "PP", "先制度")):
            metrics.addWidget(label(text, "Muted"), 0, i)
            value = label("—", "MetricValue")
            self.metric_values[text] = value
            metrics.addWidget(value, 1, i)
        details_layout.addLayout(metrics)
        details_scroll = QScrollArea()
        details_scroll.setMinimumHeight(75)
        details_scroll.setWidgetResizable(True)
        details_content = QWidget()
        description_layout = QVBoxLayout(details_content)
        description_layout.setContentsMargins(0, 0, 4, 0)
        self.move_effect = label("悬浮可预览说明；点击或用键盘选择可在这里查看完整机制。", "Effect")
        self.move_target = label("", "Muted")
        self.move_extra = label("", "Muted")
        description_layout.addWidget(self.move_effect)
        description_layout.addWidget(self.move_target)
        description_layout.addWidget(self.move_extra)
        description_layout.addStretch()
        details_scroll.setWidget(details_content)
        details_layout.addWidget(details_scroll, 1)
        self.source_button = QPushButton("在 OP.GG 查看来源 ↗")
        self.source_button.clicked.connect(self.open_move_source)
        details_layout.addWidget(self.source_button)
        self.moves_splitter.addWidget(self.details)
        self.moves_splitter.setSizes([650, 280])
        center.addWidget(self.moves_splitter, 1)
        self.moves_notice = label("招式数据离线读取，与当前图标库使用同一版本。", "Muted")
        center.addWidget(self.moves_notice)
        self.usage_update_label = label("采用率：启动时自动检查，每 24 小时后台更新一次。", "Muted")
        center.addWidget(self.usage_update_label)
        workspace.setMinimumHeight(780)
        workspace.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        workspace_scroll = PanelScrollArea()
        workspace_scroll.setWidget(workspace)
        self.splitter.addWidget(workspace_scroll)
        self.splitter.setSizes([330, 1100])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        footer = QHBoxLayout()
        self.status_label = label("准备就绪 · 拖入截图，或连接 OBS 开始。", "Muted")
        footer.addWidget(self.status_label, 1)
        self.cancel_button = QPushButton("取消当前操作")
        self.cancel_button.setObjectName("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        footer.addWidget(self.cancel_button)
        page.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        page.addWidget(self.progress)

    def _move_group(self, title):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["招式", "采用率", "属性", "分类", "威力", "命中"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        table.currentCellChanged.connect(lambda row, col, oldrow, oldcol: self.select_move(table, row))
        table.cellClicked.connect(lambda row, col: self.select_move(table, row))
        layout.addWidget(table)
        return group, table

    def set_status(self, text):
        self.status_label.setText(text)

    def _empty_team(self):
        self.team_list.clear()
        for i in range(6):
            item = QListWidgetItem(f"{i + 1:02d}   等待识别")
            item.setSizeHint(QSize(250, 48))
            self.team_list.addItem(item)
        self.correct_button.setEnabled(False)

    def _show_empty_reference(self):
        self.selected_record = None
        if self.damage_dialog is not None:
            self.damage_dialog.set_target(None)
        self.family = []
        self.hero_icon.clear()
        self.pokemon_name.setText("选择对手，查看资料")
        clear_layout(self.types_layout)
        self.matchups.show_types([])
        self.stats_table.clear()
        self.stats_table.setRowCount(0)
        self.stats_table.setColumnCount(0)
        self.speed_table.setRowCount(0)
        self.speed_table.setColumnCount(0)
        self.damage_moves, self.status_moves = [], []
        self.filter_moves()
        self.show_move(None)

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择完整的游戏截图", str(ROOT), "游戏截图 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.open_image(path)

    @Slot(str)
    def open_image(self, path):
        self._request("file", str(path))

    def open_team_editor(self):
        from .team_dialog import TeamDialog
        try:
            if self.team_dialog is None:
                self.team_dialog = TeamDialog(self.catalog, ROOT / 'user_data/teams.sqlite3', self)
                self.team_dialog.savedTeamsChanged.connect(self.team_context_changed)
            self.team_dialog.recompute()
            self.team_dialog.show()
            self.team_dialog.raise_()
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.set_status(f'队伍配置载入失败，原数据已保留：{exc}')

    def team_context_changed(self):
        if self.damage_dialog is not None:
            self.damage_dialog.refresh_teams()

    def damage_teams(self):
        from ..teams import TeamRules, TeamStore
        store = self.team_dialog.store if self.team_dialog else TeamStore(ROOT / 'user_data/teams.sqlite3', TeamRules(self.catalog))
        return store.list()

    def open_damage(self):
        from .damage_dialog import DamageDialog
        if self.damage_dialog is None:
            self.damage_dialog = DamageDialog(self.catalog, self.damage_teams, self.open_team_editor, self)
            if self.selected_record:
                self.damage_dialog.set_target(self.selected_record)
        self.damage_dialog.closing = False
        self.damage_dialog.refresh_teams()
        self.damage_dialog.show()
        self.damage_dialog.raise_()

    def _request(self, operation, payload):
        if self.busy:
            self.set_status("正在处理上一项操作；请等待完成，或先取消。")
            if operation == "sources" and self.obs_dialog:
                self.obs_dialog.set_busy(False)
            return
        self.revision += 1
        self.worker.cancelled.clear()
        if operation != "sources":
            if self.damage_dialog is not None:
                self.damage_dialog.clear_session()
            if self.team_dialog is not None:
                self.team_dialog.reset_observed()
            self.opponents = []
            self.last_result = None
            self._empty_team()
            self._show_empty_reference()
            self.preview.clear_image()
            self.input_label.setText("正在读取新截图，旧识别结果已撤下。")
        self.set_busy(True)
        self.set_status("正在连接 OBS…" if operation == "sources" else "正在采集并识别右侧对手，请稍候…")
        self.requested.emit(self.revision, operation, payload)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.open_button, self.obs_button, self.lookup_button, self.pokemon_search):
            widget.setEnabled(not busy)
        self.capture_button.setEnabled(not busy and bool(self.obs_settings.get("source")))
        self.correct_button.setEnabled(not busy and bool(self.opponents))
        self.cancel_button.setEnabled(busy)
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)

    def cancel(self):
        self.revision += 1
        self.worker.cancelled.set()
        self.cancel_button.setEnabled(False)
        self.set_status("正在取消；当前请求结束后即可继续，迟到结果不会覆盖界面。")

    @Slot(int, str, object, str)
    def _finished(self, revision, operation, result, error):
        self.set_busy(False)
        if self.closing:
            self.close()
            return
        if revision != self.revision:
            self.set_status("操作已取消。")
            if self.obs_dialog:
                self.obs_dialog.set_busy(False)
            return
        if operation == "sources":
            if self.obs_dialog:
                self.obs_dialog.show_sources(result, error)
            self.set_status(error or "OBS 连接已验证，请在连接窗口选择采集源。")
            return
        if error or not result:
            self.input_label.setText("本次截图未完成，请检查输入后重试。")
            self.set_status(error or "本次操作没有返回结果。")
            return
        self.last_result = result["recognition"]
        if self.report_path:
            try:
                save_json(self.report_path, {
                    "input": operation, "source": self.obs_settings.get("source") if operation == "obs" else None,
                    "bundle_id": self.catalog.bundle_id, "recognition": self.last_result})
            except OSError:
                pass  # A read-only output folder must not discard a successful capture.
        self.opponents = self.last_result["opponent"]
        self.preview.set_image(result["image"])
        width, height = result["image"].size
        self.input_label.setText(f"{'OBS 游戏源' if operation == 'obs' else '本地截图'} · {width} × {height}")
        if operation == "obs":
            self.obs_label.setText("已取得截图 · " + self.obs_settings["source"])
        self._render_team()
        self.correct_button.setEnabled(True)
        first = next((i for i, r in enumerate(self.opponents) if r.get("name")), 0)
        self.team_list.setCurrentRow(first)
        self.select_slot(first)
        if not self.last_result['recognized_count']:
            self.set_status("已取得画面，但六个位置均未确认。请切换到 Champions 对战选队界面，盒子或 HOME 界面不适用。")
        else:
            self.set_status(f"已识别 {self.last_result['recognized_count']}/6 · {self.last_result['elapsed_seconds']:.2f} 秒 · 点击队伍成员查看资料；待确认位置可手动修正。")

    def _render_team(self):
        self.team_list.blockSignals(True)
        self.team_list.clear()
        for index, result in enumerate(self.opponents):
            name = result.get("name") or "待确认"
            record = self.catalog.record_for_name(name)
            types = " / ".join(TYPE_NAMES[t] for t in record.get("types", [])) if record else "请手动选择对应宝可梦"
            if result.get("manual"):
                types += " · 手动修正"
            item = QListWidgetItem(f"{index + 1:02d}  {name}" + (" · 已修正" if result.get("manual") else ""))
            item.setSizeHint(QSize(250, 48))
            if record and self.catalog.sprite(record):
                item.setIcon(QIcon(str(self.catalog.sprite(record))))
            item.setToolTip(types + "\n" + (f"相似度 {result.get('similarity', 0):.3f}（不是正确率）" if not result.get("manual") else "本局手动修正，不改写图标标签或来源资料。"))
            self.team_list.addItem(item)
        self.team_list.blockSignals(False)

    def select_slot(self, row):
        if not 0 <= row < len(self.opponents):
            return
        item = self.opponents[row]
        record = self.catalog.record_for_name(item.get("name"))
        if record:
            self.show_record(record, context=f"对手槽位 {row + 1} · {'手动修正' if item.get('manual') else '识别结果'}")
        else:
            self._show_empty_reference()
            self.context_label.setText(f"对手槽位 {row + 1} · 等待确认")
            self.pokemon_name.setText("这个位置暂未确认")

    def lookup_pokemon(self):
        record = self.catalog.record_for_name(self.pokemon_search.currentText())
        if not record:
            self.set_status("请选择列表中已有的宝可梦名称。")
            return
        self.show_record(record, context="手动查阅 · 不改变对手识别结果")

    def correct_slot(self):
        row = self.team_list.currentRow()
        record = self.catalog.record_for_name(self.pokemon_search.currentText())
        if record and 0 <= row < len(self.opponents):
            self.opponents[row] = {**self.opponents[row], "name": self.catalog.display_name(record),
                                   "species_name": record["species_name"], "manual": True, "status": "confirmed"}
            self._render_team()
            self.team_list.setCurrentRow(row)
            self.set_status(f"已手动修正槽位 {row + 1}，仅作用于当前截图。")
        else:
            self.set_status("先选中对手槽位，再从搜索列表选择正确宝可梦。")

    def show_record(self, record, context="资料形态预览 · 不改变识别结果"):
        self.matchups.show_types(record.get('types',[]))
        if self.damage_dialog is not None:
            self.damage_dialog.set_target(record)
        self.selected_record = record
        self.pokemon_name.setText(self.catalog.display_name(record))
        self.context_label.setText(f"#{record['dex_number']:04d}  ·  {context}")
        self.hero_icon.clear()
        sprite = self.catalog.sprite(record)
        if sprite:
            self.hero_icon.setPixmap(QPixmap(str(sprite)).scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        clear_layout(self.types_layout)
        for kind in record.get("types", []):
            self.types_layout.addWidget(type_badge(kind))
        if not record.get("types"):
            self.types_layout.addWidget(label("该形态属性资料缺失", "Muted"))
        self.family = self.catalog.form_family(record)
        self._render_stats()
        self.damage_moves, self.status_moves, notice = self.catalog.learnset(record)
        self.moves_notice.setText(notice)
        self.filter_moves()
        moves = self.damage_moves or self.status_moves
        self.show_move(moves[0] if moves else None)

    def _render_stats(self):
        self.stats_table.setColumnCount(len(self.family) + 1)
        self.stats_table.setRowCount(8)
        headers = ["基础能力"] + [self.catalog.display_name(r) for r in self.family]
        self.stats_table.setHorizontalHeaderLabels(headers)
        stat_rows = [("属性", None), ("HP", "hp"), ("攻击", "attack"), ("防御", "defense"),
                     ("特攻", "special_attack"), ("特防", "special_defense"), ("速度", "speed"), ("总和", "total")]
        for row, (title, key) in enumerate(stat_rows):
            self.stats_table.setRowHeight(row, 27)
            self.stats_table.setItem(row, 0, QTableWidgetItem(title))
            for col, record in enumerate(self.family, 1):
                if key is None:
                    value = " / ".join(TYPE_NAMES[t] for t in record.get("types", [])) or "资料缺失"
                else:
                    value = str(record["base_stat_total"] if key == "total" else record["base_stats"][key])
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if record is self.selected_record:
                    item.setBackground(QColor("#eaf6f0"))
                if key == "speed":
                    item.setForeground(QColor("#137665"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.stats_table.setItem(row, col, item)
        self._render_speed()
        self._reference_note()

    def _reference_note(self):
        if self.reference_tabs.currentIndex() == 1:
            self.form_note.setText("50级参考档位，非对手已知配置；无投为0点、满速为32点。下降指减速性格；未计轻装、顺风、天气或能力等级。")
        else:
            self.form_note.setText("点击列标题查看对应形态。这里是种族值，非实际速度；Mega 列仅作预览。" if len(self.family) > 1 else "当前资料中没有对应的 Mega 分支。种族值不等于对战中的实际能力。")

    def _render_speed(self):
        if not hasattr(self, "speed_table") or not self.family:
            return
        records = list(self.family)
        compare = self.catalog.record_for_name(self.speed_compare.currentText())
        if compare and compare not in records:
            records.append(compare)
        table = self.speed_table
        table.setColumnCount(len(records) + 1)
        table.setRowCount(len(SPEED_TIERS))
        table.setHorizontalHeaderLabels(["速度档位"] + [self.catalog.display_name(r) for r in records])
        values = [speed_lines(r["base_stats"]["speed"]) for r in records]
        for row, (name, _, _, _, condition) in enumerate(SPEED_TIERS):
            table.setRowHeight(row, 30)
            item = QTableWidgetItem(name)
            item.setToolTip(condition)
            table.setItem(row, 0, item)
            for col, record in enumerate(records, 1):
                value = QTableWidgetItem(str(values[col - 1][row]))
                value.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                value.setToolTip("50级 · " + condition)
                if record is self.selected_record:
                    value.setBackground(QColor("#eaf6f0"))
                table.setItem(row, col, value)

    def reload_usage(self):
        error = self.refresh_usage_view()
        self.set_status(error or "已载入本地最新采用率快照。联网更新可运行 update_usage_data.bat。")

    def refresh_usage_view(self):
        error = self.catalog.reload_usage()
        if self.damage_dialog is not None:
            self.damage_dialog.refresh_statistics()
        if self.selected_record:
            self.damage_moves, self.status_moves, notice = self.catalog.learnset(self.selected_record)
            self.moves_notice.setText(notice)
            self.filter_moves()
        return error

    def select_form_column(self, column):
        if 1 <= column <= len(self.family):
            self.show_record(self.family[column - 1])

    def filter_moves(self):
        term = self.move_search.text().strip().casefold()
        for group, table, moves, title in [(self.damage_group, self.damage_table, getattr(self, "damage_moves", []), "伤害招式"),
                                          (self.status_group, self.status_table, getattr(self, "status_moves", []), "变化招式")]:
            filtered = [m for m in moves if term in (m["name"] + TYPE_NAMES[m["type"]] + m["description"]).casefold()]
            table.blockSignals(True)
            table.setRowCount(len(filtered))
            for row, move in enumerate(filtered):
                rate = move.get("usage_percent")
                values = [move["name"], f"{rate:g}%" if rate is not None else "—", TYPE_NAMES[move["type"]], CATEGORIES[move["category"]], power_label(move), accuracy_label(move)]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, move)
                    item.setToolTip(move_tooltip(move))
                    if col > 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col == 2:
                        item.setForeground(QColor(TYPE_COLORS[move["type"]]))
                    table.setItem(row, col, item)
                table.setRowHeight(row, 33)
            group.setTitle(f"{title}   {len(filtered)} / {len(moves)}")
            table.blockSignals(False)

    def select_move(self, table, row):
        item = table.item(row, 0)
        if item:
            self.show_move(item.data(Qt.ItemDataRole.UserRole))

    def show_move(self, move):
        self.current_move = move
        clear_layout(self.move_tags)
        self.source_button.setEnabled(bool(move))
        if not move:
            self.move_title.setText("点击任意招式")
            self.move_effect.setText("悬浮可预览说明；点击或用键盘选择可在这里查看完整机制。")
            self.move_target.setText("")
            self.move_extra.setText("")
            for item in self.metric_values.values():
                item.setText("—")
            return
        self.move_title.setText(move["name"])
        self.move_tags.addWidget(type_badge(move["type"]))
        self.move_tags.addWidget(label(CATEGORIES[move["category"]], "Muted"))
        values = [power_label(move), accuracy_label(move), str(move.get("pp") if move.get("pp") is not None else "未知"),
                  f"{move['priority']:+d}" if move.get("priority") is not None else "未知"]
        for title, value in zip(self.metric_values, values):
            self.metric_values[title].setText(value)
        self.move_effect.setText(move["description"])
        self.move_target.setText("作用目标：" + TARGETS.get(move.get("target"), "来源未说明"))
        traits = move.get("moveTraits", [])
        notes = []
        if "contact" in traits:
            notes.append("接触招式")
        elif "non-contact" in traits:
            notes.append("非接触招式")
        if move.get("power") is None and move["category"] != "status":
            notes.append("没有固定威力数值，请按效果理解其计算方式。")
        if move.get("accuracy") is None:
            notes.append("来源未给数值命中率；可能无需命中判定或使用特殊机制，详见效果。")
        self.move_extra.setText("\n".join(notes))

    def open_move_source(self):
        if self.current_move:
            QDesktopServices.openUrl(QUrl(self.current_move["source_url"]))

    def configure_obs(self):
        if self.obs_dialog is not None:
            self.obs_dialog.raise_()
            self.obs_dialog.activateWindow()
            return
        dialog = ObsDialog(self.obs_settings, self)
        self.obs_dialog = dialog
        dialog.connectRequested.connect(lambda settings: self._request("sources", settings))
        dialog.accepted.connect(self.apply_obs_settings)
        dialog.finished.connect(lambda _: self._close_obs_dialog(dialog))
        dialog.show()

    def apply_obs_settings(self):
        self.obs_settings = self.obs_dialog.settings()
        try:
            save_json(self.settings_path, {k: v for k, v in self.obs_settings.items() if k != "password"})
        except OSError:
            self.set_status("连接信息已在本次运行生效，但设置文件保存失败。")
        self.obs_label.setText("已选择 · " + self.obs_settings["source"])
        self.capture_button.setEnabled(not self.busy and bool(self.obs_settings["source"]))

    def _close_obs_dialog(self, dialog):
        if self.obs_dialog is dialog:
            self.obs_dialog = None
        dialog.deleteLater()

    def capture_obs(self):
        self._request("obs", dict(self.obs_settings))

    def closeEvent(self, event):
        if self.damage_dialog is not None and self.damage_dialog.worker is not None:
            self.damage_dialog.worker.finished.connect(self.close)
            self.damage_dialog.close()
            event.ignore()
            return
        if self.damage_dialog is not None:
            self.damage_dialog.close()
        if self.team_dialog is not None and not self.team_dialog.close():
            event.ignore()
            return
        if hasattr(self, "usage_updater"):
            self.usage_updater.stop()
        if self.busy:
            self.closing = True
            self.cancel()
            event.ignore()
            return
        self.thread.quit()
        self.thread.wait(5000)
        event.accept()
