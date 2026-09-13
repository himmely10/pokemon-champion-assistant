"""Two-image local OCR, with review before creating an unsaved team draft."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QScrollArea, QSlider, QMessageBox)

from ..team_import import ScreenshotImporter
from ..teams import STATS
from .team_dialog import combo, select, value
from .dialog_layout import fit_dialog
from .obs_dialog import ObsDialog
from ..capture.obs import ObsCapture, local_obs_settings


class ObsImportWorker(QThread):
    def __init__(self, settings, operation, parent=None):
        super().__init__(parent)
        self.settings, self.operation = dict(settings), operation
        self.result, self.error = None, ''

    def run(self):
        try:
            self.result = getattr(ObsCapture(), self.operation)(self.settings)
        except Exception:
            self.error = 'OBS 读取失败，请核对服务器开关、地址、端口、密码及采集源。'
        finally:
            self.settings.clear()


class ImportWorker(QThread):
    progress = Signal(str)

    def __init__(self, rules, paths, parent=None):
        super().__init__(parent)
        self.rules, self.paths = rules, paths
        self.pages, self.error = None, ''

    def run(self):
        try:
            def progress(text):
                if self.isInterruptionRequested():
                    raise ValueError('已取消截图导入。')
                self.progress.emit(text)
            progress('正在准备本地 OCR（重复导入会复用模型）…')
            importer = ScreenshotImporter(self.rules)
            progress('OCR 已就绪，正在读取截图…')
            self.pages = [importer.read_page(self.paths[mode], mode, progress) for mode in ('ability', 'status')]
            if self.isInterruptionRequested():
                self.pages = None
                raise ValueError('已取消截图导入。')
        except Exception as exc:
            self.error = str(exc)


class TeamImportDialog(QDialog):
    def __init__(self, rules, parent=None, obs_settings=None):
        super().__init__(parent)
        self.rules = rules
        self.paths = {}
        self.pages = None
        self.worker = None
        self.obs_worker = None
        self.obs_settings_provider = obs_settings
        self.selected_obs_settings = None
        self.obs_dialog = None
        self.capture_files = TemporaryDirectory(prefix='champion-team-')
        self.closing = False
        self.result_draft = None
        self.setWindowTitle('从队伍详情截图导入 · 本地 OCR')
        fit_dialog(self, 1220, 860)
        layout = QVBoxLayout(self)
        help_text = QLabel('选择同一队伍的两张完整截图。识别在本机运行；导入只创建草稿，核对后再保存。')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.path_edits, self.file_buttons = {}, []
        for mode, title in [('ability', '能力截图（特性／道具／四招）'), ('status', '状态截图（培养点／性格）')]:
            row = QHBoxLayout()
            button = QPushButton(title)
            button.clicked.connect(lambda _, m=mode: self.choose(m))
            self.file_buttons.append(button)
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setPlaceholderText('选择 PNG / JPG / WebP 文件…')
            self.path_edits[mode] = edit
            row.addWidget(button)
            row.addWidget(edit, 1)
            obs_button = QPushButton('从 OBS 截图')
            obs_button.setObjectName('obs_' + mode)
            obs_button.clicked.connect(lambda _, m=mode: self.capture_obs(m))
            self.file_buttons.append(obs_button)
            row.addWidget(obs_button)
            layout.addLayout(row)
        self.previews = QTabWidget()
        self.preview_labels = {}
        for mode, title in [('ability', '能力原图'), ('status', '状态原图')]:
            label = QLabel('选择图片后显示原图预览')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(140)
            label.setMaximumHeight(170)
            self.preview_labels[mode] = label
            self.previews.addTab(label, title)
        layout.addWidget(self.previews)
        zoom = QPushButton('放大查看当前原图（可缩放与滚动）')
        zoom.clicked.connect(self.open_preview)
        layout.addWidget(zoom)
        self.run_button = QPushButton('识别两张截图')
        self.run_button.clicked.connect(self.start)
        layout.addWidget(self.run_button)
        code_row = QHBoxLayout()
        self.codes = []
        for title in ('能力页队伍码', '状态页队伍码'):
            code_row.addWidget(QLabel(title))
            box = QLineEdit()
            box.setMaxLength(10)
            box.setPlaceholderText('核对 0/O、1/I')
            self.codes.append(box)
            code_row.addWidget(box)
        layout.addLayout(code_row)
        self.table = QTableWidget(6, 7)
        self.table.setHorizontalHeaderLabels(['能力页身份', '状态页身份', '培养点 HP/攻/防/特攻/特防/速', '性格', '特性', '道具', '四招'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.status = QLabel('等待选择两张截图。支持这类六张紫色卡片布局；遮挡或裁剪可能需要人工补全。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.review = QCheckBox('已对照原图核对队伍码与两页身份；其余字段将在队伍编辑器继续核对')
        layout.addWidget(self.review)
        self.use_button = QPushButton('载入为新队伍草稿')
        self.use_button.setEnabled(False)
        self.use_button.setObjectName('Primary')
        self.use_button.clicked.connect(self.use_draft)
        layout.addWidget(self.use_button)
        self.review.toggled.connect(lambda checked: self.use_button.setEnabled(checked and self.pages is not None))
        for box in self.codes:
            box.textChanged.connect(lambda _: self.review.setChecked(False))

    def choose(self, mode):
        path, _ = QFileDialog.getOpenFileName(self, '选择队伍详情截图', '', '图片 (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.set_path(mode, path)

    def current_obs_settings(self):
        if self.selected_obs_settings is not None:
            return dict(self.selected_obs_settings)
        provided = self.obs_settings_provider
        if provided is not None:
            settings = provided() if callable(provided) else provided
            if settings:
                return dict(settings)
        ancestor = self.parent()
        while ancestor is not None:
            settings = getattr(ancestor, 'obs_settings', None)
            if isinstance(settings, dict):
                return dict(settings)
            ancestor = ancestor.parent()
        return local_obs_settings(include_password=True) or {}

    def capture_obs(self, mode):
        if self.worker or self.obs_worker:
            return
        settings = self.current_obs_settings()
        if settings.get('source'):
            self.start_obs(settings, 'screenshot', mode)
            return
        dialog = ObsDialog(settings, self)
        self.obs_dialog = dialog
        dialog.connectRequested.connect(lambda s: self.start_obs(s, 'sources', mode))
        def accepted():
            self.selected_obs_settings = dialog.settings()
            self.start_obs(self.selected_obs_settings, 'screenshot', mode)
        dialog.accepted.connect(accepted)
        dialog.open()

    def start_obs(self, settings, operation, mode):
        if self.worker or self.obs_worker:
            return
        self.pages = None
        self.review.setChecked(False)
        self.use_button.setEnabled(False)
        for button in self.file_buttons + [self.run_button]:
            button.setEnabled(False)
        self.status.setText('正在读取 OBS 采集源…' if operation == 'sources' else '正在从 OBS 获取截图…')
        worker = ObsImportWorker(settings, operation, self)
        self.obs_worker = worker
        def finished():
            self.obs_worker = None
            for button in self.file_buttons + [self.run_button]:
                button.setEnabled(True)
            if self.closing:
                worker.deleteLater()
                self.capture_files.cleanup()
                super(TeamImportDialog, self).reject()
                return
            if operation == 'sources':
                self.obs_dialog.show_sources(worker.result, worker.error)
            elif worker.error:
                self.status.setText(worker.error)
            else:
                path = Path(self.capture_files.name) / (mode + '.png')
                worker.result.save(path)
                self.set_path(mode, path)
                self.previews.setCurrentIndex(0 if mode == 'ability' else 1)
                self.status.setText('OBS 截图已显示，请核对页面。两页准备好后点击“识别两张截图”。')
            worker.deleteLater()
        worker.finished.connect(finished)
        worker.start()

    def set_path(self, mode, path):
        self.paths[mode] = path
        self.path_edits[mode].setText(str(path))
        self.preview_labels[mode].setPixmap(QPixmap(str(path)).scaled(950, 165, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.pages = None
        self.review.setChecked(False)
        self.use_button.setEnabled(False)
        self.table.clearContents()
        for box in self.codes:
            box.clear()

    def open_preview(self):
        mode = ('ability', 'status')[self.previews.currentIndex()]
        if mode not in self.paths:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('核对原图 · 拖动滑块缩放')
        fit_dialog(dialog, 1150, 760)
        layout = QVBoxLayout(dialog)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(25, 150)
        layout.addWidget(slider)
        scroll = QScrollArea()
        label = QLabel()
        scroll.setWidget(label)
        layout.addWidget(scroll, 1)
        original = QPixmap(str(self.paths[mode]))
        def scale(percent):
            pixmap = original.scaledToWidth(round(original.width()*percent/100), Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pixmap)
            label.resize(pixmap.size())
        slider.valueChanged.connect(scale)
        slider.setValue(50)
        dialog.exec()

    def start(self):
        if self.obs_worker:
            return
        if self.worker and self.worker.isRunning():
            return
        if len(self.paths) != 2:
            self.status.setText('请选择能力和状态两张截图。')
            return
        self.pages = None
        self.review.setChecked(False)
        self.use_button.setEnabled(False)
        self.table.clearContents()
        for box in self.codes: box.clear()
        for button in self.file_buttons + [self.run_button]: button.setEnabled(False)
        self.status.setText('正在加载本地 OCR 模型…')
        self.worker = ImportWorker(self.rules, dict(self.paths), self)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.finished_ocr)
        self.worker.start()

    def finished_ocr(self):
        worker = self.worker
        self.worker = None
        for button in self.file_buttons + [self.run_button]: button.setEnabled(True)
        if self.closing:
            worker.deleteLater()
            super().reject()
            return
        if worker.error:
            self.status.setText('识别未完成：' + worker.error)
        else:
            self.show_pages(worker.pages)
            self.notice_box = QMessageBox(QMessageBox.Icon.Information, '队伍识别完成',
                '能力与状态两页已经识别完成。请核对队伍码、宝可梦身份和带问号的字段，再生成队伍草稿。',
                QMessageBox.StandardButton.Ok, self)
            self.notice_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.notice_box.open()
        worker.deleteLater()

    def show_pages(self, pages):
        self.pages = deepcopy(pages)
        self.review.setChecked(False)
        self.use_button.setEnabled(False)
        for box, page in zip(self.codes, pages): box.setText(page['team_code'] or '')
        alternate_count = 0
        for row, (a, s) in enumerate(zip(*[p['members'] for p in pages])):
            for col, entry in enumerate((a, s)):
                chooser = combo(self.rules.choices(), '未确认：请对照原图选择')
                select(chooser, entry['member']['identity'])
                chooser.setToolTip(json.dumps(entry['evidence']['name'], ensure_ascii=False))
                chooser.currentTextChanged.connect(lambda _: self.review.setChecked(False))
                self.table.setCellWidget(row, col, chooser)
                alternate_count += bool(entry['evidence']['name'].get('used_alternate'))
            am, sm = a['member'], s['member']
            values = [
                '/'.join(str(sm['points'][k]) if sm['points'][k] is not None else '?' for k in STATS),
                self.rules.options['natures'].get(sm['nature'], {}).get('name', '待确认'),
                self.rules.options['abilities'].get(am['ability'], {}).get('name', '待确认'),
                self.rules.options['items'].get(am['item'], {}).get('name', '待确认'),
                ' / '.join(self.rules.catalog.moves.get(k, {}).get('name', '?') for k in am['moves'])]
            for col, text in enumerate(values, 2):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2:
                    detail = '\n'.join(f"{name}：面板 {s['evidence']['panel_stats'][key]['value']}，培养点 {sm['points'][key]}"
                                       for key, name in STATS.items())
                elif col == 3:
                    detail = '\n'.join(f"{STATS[key]}：{mark or '未检测到修正'}" for key, mark in s['evidence']['marks'].items())
                else:
                    detail = json.dumps(a['evidence'][{4:'ability', 5:'item', 6:'moves'}[col]], ensure_ascii=False, indent=2)
                item.setToolTip(detail)
                self.table.setItem(row, col, item)
        self.table.resizeRowsToContents()
        self.status.setText(f'已生成识别结果，{alternate_count} 项身份使用局部增强重识别。请特别核对队伍码的 0/O、性别形态和性格箭头；问号表示未知。面板数字见单元格悬浮证据。')

    def use_draft(self):
        if not self.pages or not self.review.isChecked():
            return
        pages = deepcopy(self.pages)
        try:
            import re
            for col, page in enumerate(pages):
                code = self.codes[col].text().strip().upper()
                if not re.fullmatch('[A-Z0-9]{10}', code):
                    raise ValueError('队伍码需要十位字母或数字；请对照两张原图分别核对。')
                page['team_code'] = code
                page['code_reviewed'] = True
                for row, entry in enumerate(page['members']):
                    identity = value(self.table.cellWidget(row, col))
                    if identity != entry['member']['identity']:
                        entry['evidence']['manual_identity'] = identity
                        # Fields tied to the previous identity cannot follow a correction.
                        entry['member'].update(identity=identity, ability=None, moves=[None]*4)
            importer = ScreenshotImporter(self.rules, ocr=False)
            self.result_draft = importer.combine(*pages)
            self.result_draft['draft']['import_source']['identity_reviewed'] = True
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.accept()

    def closeEvent(self, event):
        if self.obs_worker and self.obs_worker.isRunning():
            self.closing = True
            self.status.setText('等待当前 OBS 请求结束…')
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.worker.requestInterruption()
            self.status.setText('正在取消，等待当前文字识别结束…')
            event.ignore()
        else:
            self.capture_files.cleanup()
            event.accept()

    def reject(self):
        if (self.worker and self.worker.isRunning()) or (self.obs_worker and self.obs_worker.isRunning()):
            self.close()
        else:
            super().reject()
