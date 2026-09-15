"""Saved-team editor and independent, manually confirmed current roster."""
from copy import deepcopy
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QInputDialog)

from ..teams import STATS, TeamRules, TeamStore, blank_member, match_team
from ..data.moves import move_tooltip, power_label, accuracy_label
from ..data.storage import TYPE_NAMES
from .matchups import MatchupLabel
from .dialog_layout import fit_dialog


def combo(choices, unknown='未知 / 未填写'):
    box = QComboBox()
    box.setEditable(True)
    box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    box.setMinimumContentsLength(12)
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.addItem(unknown, None)
    for name, key in choices:
        box.addItem(name, key)
    box.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    box.completer().setFilterMode(Qt.MatchFlag.MatchContains)
    return box


def value(box):
    # Typed but unselected text must never reuse the previous selection's identity.
    index = box.currentIndex()
    if index < 0 or box.currentText() != box.itemText(index):
        raise ValueError('请从下拉列表选择完整条目；未填写请选“未知”。')
    return box.currentData()


def select(box, key):
    index = box.findData(key)
    if index < 0:
        box.addItem(f'资料缺失：{key}', key)
        index = box.count() - 1
    box.setCurrentIndex(index)


class MemberEditor(QWidget):
    def __init__(self, rules, changed):
        super().__init__()
        self.rules, self.changed = rules, changed
        self.loading = False
        layout = QGridLayout(self)
        self.pokemon = combo(rules.choices(), '未登记此槽位')
        layout.addWidget(QLabel('宝可梦 / 形态'), 0, 0)
        layout.addWidget(self.pokemon, 0, 1, 1, 3)
        self.points = {}
        for i, (key, name) in enumerate(STATS.items()):
            box = QSpinBox()
            box.setRange(-1, rules.options['point_rules']['per_stat'])
            box.setSpecialValueText(name+'未填写')
            box.setValue(-1)
            self.points[key] = box
            layout.addWidget(QLabel(name), 1 + i // 2, (i % 2) * 2)
            layout.addWidget(box, 1 + i // 2, (i % 2) * 2 + 1)
            box.valueChanged.connect(self.edited)
        self.total = QLabel()
        layout.addWidget(self.total, 4, 0, 1, 4)
        self.nature = combo([(self.nature_label(n), k) for k, n in rules.options['natures'].items()], '性格未填写')
        self.ability = combo([], '特性未填写')
        self.item = combo([('无道具（已确认）', 'none')] + [(v['name'], k) for k, v in rules.options['items'].items()], '道具未填写')
        for row, (name, box) in enumerate([('性格', self.nature), ('特性', self.ability), ('道具', self.item)], 5):
            layout.addWidget(QLabel(name), row, 0)
            layout.addWidget(box, row, 1, 1, 3)
            box.currentTextChanged.connect(self.edited)
        self.moves = [combo([], f'招式 {i+1} 未填写') for i in range(4)]
        for i, box in enumerate(self.moves):
            layout.addWidget(QLabel(f'招式 {i + 1}'), 8 + i, 0)
            layout.addWidget(box, 8 + i, 1, 1, 3)
            box.currentTextChanged.connect(self.edited)
        self.matchups = MatchupLabel()
        layout.addWidget(self.matchups,12,0,1,4)
        layout.setRowStretch(13, 1)
        self.pokemon.currentIndexChanged.connect(self.pokemon_changed)
        self.pokemon.editTextChanged.connect(self.edited)
        self.edited()

    @staticmethod
    def nature_label(n):
        names = {**STATS, 'spAttack': '特攻', 'spDefense': '特防'}
        return n['name'] + (f"（+{names[n['increased']]} / −{names[n['decreased']]}）" if n['increased'] else '（无修正）')

    def pokemon_changed(self):
        identity = self.pokemon.currentData()
        self.loading = True
        # Changing the identity discards the previous member's build, even if moves overlap.
        for box in self.points.values():
            box.setValue(-1)
        self.nature.setCurrentIndex(0)
        self.item.setCurrentIndex(0)
        self.ability.clear()
        self.ability.addItem('特性未填写', None)
        for key in self.rules.ability_keys(identity):
            self.ability.addItem(self.rules.options['abilities'].get(key, {}).get('name', key), key)
        for i, box in enumerate(self.moves):
            box.clear()
            box.addItem(f'招式 {i+1} 未填写', None)
            for key in self.rules.move_keys(identity):
                m = self.rules.catalog.moves[key]
                box.addItem(f"{m['name']} · {TYPE_NAMES[m['type']]} · {power_label(m)} / {accuracy_label(m)}", key)
                box.setItemData(box.count() - 1, move_tooltip(m), Qt.ItemDataRole.ToolTipRole)
        self.loading = False
        self.edited()

    def edited(self, *_):
        if self.loading:
            return
        values = [b.value() for b in self.points.values()]
        try:record=self.rules.record(value(self.pokemon))
        except ValueError:record=None
        self.matchups.show_types(record['types'] if record else [])
        self.total.setText(f'已填培养点：{sum(max(0, v) for v in values)} / 66 · 未填 {values.count(-1)} 项')
        self.changed()

    def read(self):
        identity = value(self.pokemon)
        if identity is None:
            return None
        return {'identity': identity, 'points': {k: None if b.value() < 0 else b.value() for k, b in self.points.items()},
                'nature': value(self.nature), 'ability': value(self.ability), 'item': value(self.item),
                'moves': [value(b) for b in self.moves]}

    def load(self, member):
        select(self.pokemon, member['identity'])
        self.pokemon_changed()
        self.loading = True
        for k, b in self.points.items():
            b.setValue(-1 if member['points'][k] is None else member['points'][k])
        for field in ('nature', 'ability', 'item'):
            select(getattr(self, field), member[field])
        for box, key in zip(self.moves, member['moves']):
            select(box, key)
        self.loading = False
        self.edited()


class TeamDialog(QDialog):
    matchChanged = Signal()
    savedTeamsChanged = Signal()
    def __init__(self, catalog, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle('我方队伍 · 保存配置与整队校验')
        fit_dialog(self, 1060, 800)
        self.rules = TeamRules(catalog)
        self.store = TeamStore(path, self.rules)
        self.active = None
        self.import_source = None
        self.loading = True
        self.dirty = False
        self.result = {'matched': False, 'builds': {}}
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("DialogViewport")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        tools = QHBoxLayout()
        self.saved = QComboBox()
        self.saved.addItem('选择已保存队伍', None)
        tools.addWidget(self.saved, 1)
        for text, fn in [('新建', self.new_team), ('重命名', self.rename_team), ('截图导入', self.import_screenshots), ('另存副本', self.copy_team), ('删除', self.delete_team)]:
            button = QPushButton(text)
            button.clicked.connect(fn)
            tools.addWidget(button)
        layout.addLayout(tools)
        title = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.name.setPlaceholderText('队伍名称，例如：顺风队 M6')
        self.mode = QComboBox()
        self.mode.addItem('完整登记：六只必须全部对应', 'full')
        self.mode.addItem('明确部分登记：仅保存一至五只', 'partial')
        title.addWidget(self.name, 1)
        title.addWidget(self.mode)
        layout.addLayout(title)
        note = QLabel('先登记成员，再逐步补全配置。未填培养点保留为未知；完整六人名单即使只填四只配置，也必须按六只匹配。')
        note.setWordWrap(True)
        layout.addWidget(note)
        columns = QHBoxLayout()
        self.tabs = QTabWidget()
        self.editors = []
        for i in range(6):
            editor = MemberEditor(self.rules, self.mark_dirty)
            self.editors.append(editor)
            self.tabs.addTab(editor, f'成员 {i + 1}')
        sections = QTabWidget()
        sections.addTab(self.tabs, '培养配置')
        verification = QWidget()
        sections.addTab(verification, '整队匹配验证（可选）')
        columns.addWidget(sections, 1)
        right = QVBoxLayout(verification)
        heading = QLabel('可选：整队匹配验证')
        right.addWidget(heading)
        hint = QLabel('伤害计算直接使用所选预存队伍，无需填写此处。此功能保留用于验证阵容匹配规则；当前尚未自动识别我方。')
        hint.setWordWrap(True)
        right.addWidget(hint)
        self.observed = []
        for i in range(6):
            row = QHBoxLayout()
            row.addWidget(QLabel(str(i + 1)))
            pokemon = combo(self.rules.choices(), '身份未知 / 未确认')
            item = combo([('无道具（已确认）', 'none')] + [(v['name'], k) for k, v in self.rules.options['items'].items()], '道具未知')
            row.addWidget(pokemon, 1)
            row.addWidget(item, 1)
            right.addLayout(row)
            self.observed.append((pokemon, item))
            pokemon.currentIndexChanged.connect(lambda _, box=item: box.setCurrentIndex(0))
            pokemon.currentTextChanged.connect(self.recompute)
            item.currentTextChanged.connect(self.recompute)
        reset = QPushButton('清空当前阵容确认')
        reset.clicked.connect(self.reset_observed)
        right.addWidget(reset)
        self.match_label = QLabel()
        self.match_label.setWordWrap(True)
        right.addWidget(self.match_label)
        self.build_view = QTextEdit()
        self.build_view.setReadOnly(True)
        right.addWidget(self.build_view, 1)
        layout.addLayout(columns, 1)
        self.message = QLabel('')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        self.save_button = QPushButton('保存队伍')
        self.save_button.setObjectName('Primary')
        self.save_button.clicked.connect(self.save_team)
        footer = QHBoxLayout()
        footer.addWidget(QLabel('修改后保存，伤害页会自动刷新。'), 1)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)
        self.name.textChanged.connect(self.mark_dirty)
        self.mode.currentIndexChanged.connect(self.mark_dirty)
        self.saved.currentIndexChanged.connect(self.choose_team)
        self.refresh_list()
        self.loading = False
        self.recompute()

    def refresh_list(self, selected=None):
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem('选择已保存队伍', None)
        for team in self.store.list():
            self.saved.addItem(team['name'], team['id'])
        self.saved.setCurrentIndex(max(0, self.saved.findData(selected)))
        self.saved.blockSignals(False)

    def mark_dirty(self, *_):
        if self.loading:
            return
        self.dirty = True
        for i, e in enumerate(self.editors):
            self.tabs.setTabText(i, f'{i + 1} ' + self.rules.name(e.pokemon.currentData()))
        self.recompute()

    def may_discard(self):
        return not self.dirty or QMessageBox.question(self, '未保存的修改', '放弃当前未保存的修改？') == QMessageBox.StandardButton.Yes

    def choose_team(self):
        if not self.may_discard():
            self.refresh_list(self.active['id'] if self.active else None)
            return
        chosen = self.saved.currentData()
        self.load_team(next((t for t in self.store.list() if t['id'] == chosen), None))

    def load_team(self, team, *, as_draft=False):
        self.loading = True
        self.active = deepcopy(team) if not as_draft else None
        self.import_source = deepcopy(team.get('import_source')) if team else None
        self.name.setText(team['name'] if team else '')
        select(self.mode, team['registration'] if team else 'full')
        members = team['members'] if team else []
        for i, editor in enumerate(self.editors):
            editor.load(members[i] if i < len(members) else blank_member())
            self.tabs.setTabText(i, f'{i + 1} ' + self.rules.name(editor.pokemon.currentData()))
        self.loading, self.dirty = False, as_draft
        self.message.setText('')
        self.recompute()

    def new_team(self):
        if self.may_discard():
            self.refresh_list()
            self.load_team(None)

    def draft(self):
        members = [e.read() for e in self.editors]
        return {**(self.active or {}), 'import_source': deepcopy(self.import_source), 'name': self.name.text(), 'registration': self.mode.currentData(),
                'members': [m for m in members if m is not None]}

    def import_screenshots(self):
        if not self.may_discard():
            return
        from .team_import_dialog import TeamImportDialog
        dialog = TeamImportDialog(self.rules, self, obs_settings=lambda: getattr(self.parent(), 'obs_settings', {}))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.result_draft
            self.refresh_list()
            self.load_team(result['draft'], as_draft=True)
            self.reset_observed()
            self.message.setText(result['notice'] + ' ' + ' '.join(result['warnings']))
        dialog.deleteLater()

    def copy_team(self):
        self.active = None
        self.name.setText(self.name.text() + ' 副本')
        self.refresh_list()
        self.mark_dirty()

    def save_team(self):
        try:
            team = self.store.save(self.draft())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.message.setText(f'保存失败：{exc}')
            self.show_warning('队伍未保存', str(exc))
            return
        self.active, self.dirty = team, False
        self.refresh_list(team['id'])
        self.message.setText(f"已保存「{team['name']}」· 版本 {team['revision']}。")
        self.recompute()
        self.savedTeamsChanged.emit()
        from ..damage import DamageService
        service = DamageService(self.rules.catalog)
        problems = []
        for i, member in enumerate(team['members'], 1):
            issues = service.readiness(member)
            if issues:problems.append(f"第 {i} 槽 · {self.rules.name(member['identity'])}\n"+'\n'.join(issues))
        if problems:
            self.message.setText(f"⚠ 已保存「{team['name']}」，部分配置需要补充或选择战斗条件才能计算。")
            self.show_warning('已保存 · 伤害计算需要注意', '\n\n'.join(problems))
        else:
            previous = getattr(self, 'success_box', None)
            if previous is not None:
                previous.close()
            self.success_box = QMessageBox(QMessageBox.Icon.Information, '队伍保存成功',
                f"已保存「{team['name']}」· 版本 {team['revision']}。伤害页面会自动读取最新配置。",
                QMessageBox.StandardButton.Ok, self)
            self.success_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.success_box.open()

    def show_warning(self, title, text):
        previous = getattr(self, 'warning_box', None)
        if previous is not None:
            previous.close()
        self.warning_box = QMessageBox(QMessageBox.Icon.Warning, title, text,
            QMessageBox.StandardButton.Ok, self)
        self.warning_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.warning_box.open()

    def rename_team(self):
        name, accepted = QInputDialog.getText(self, '重命名队伍', '新队伍名称（保存时生效）', text=self.name.text())
        if not accepted:return
        if not 1 <= len(name.strip()) <= 80:
            self.show_warning('名称无效', '队伍名称须为 1–80 个字符。');return
        self.name.setText(name.strip())
        self.message.setText('名称已修改，请点击底部“保存队伍”；当前其他修改会一并保存。')

    def delete_team(self):
        if not self.active or QMessageBox.question(self, '删除队伍', '删除这支预存队伍？') != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(self.active)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.message.setText(str(exc))
            return
        self.refresh_list()
        self.load_team(None)
        self.savedTeamsChanged.emit()

    def reset_observed(self):
        self.loading = True
        for pokemon, item in self.observed:
            pokemon.setCurrentIndex(0)
            item.setCurrentIndex(0)
        self.loading = False
        self.recompute()

    def recompute(self, *_):
        previous = deepcopy(self.result)
        self._recompute()
        if previous != self.result:
            self.matchChanged.emit()

    def _recompute(self):
        if self.loading:
            return
        self.result = {'matched': False, 'builds': {}}
        self.build_view.clear()
        if self.dirty or not self.active:
            self.match_label.setText('尚未引用配置：请先保存并选择队伍。')
            return
        try:
            observed = [{'identity': value(p), 'item': value(i)} for p, i in self.observed]
            # Read the current revision, so another editor cannot authorize stale builds.
            current = next((t for t in self.store.list() if t['id'] == self.active['id']), None)
            if not current or current['revision'] != self.active['revision']:
                raise ValueError('预存队伍已更新或删除，请重新选择。')
            self.result = match_team(current, observed, self.rules)
            self.match_label.setText(self.result['reason'])
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.match_label.setText(str(exc))
            return
        lines = []
        for slot, member in self.result['builds'].items():
            def named(field, group):
                key = member[field]
                return '无道具' if key == 'none' else self.rules.options[group].get(key, {}).get('name', '未知')
            lines.append(f"第 {slot + 1} 槽 · {self.rules.name(member['identity'])}")
            lines.append(' / '.join(f"{STATS[k]} {v if v is not None else '未知'}" for k, v in member['points'].items()))
            lines.append(f"{named('nature', 'natures')} · {named('ability', 'abilities')} · {named('item', 'items')}")
            lines.append(' / '.join(self.rules.catalog.moves.get(k, {}).get('name', '未知') for k in member['moves']))
            lines.append('')
        self.build_view.setPlainText('\n'.join(lines))

    def closeEvent(self, event):
        if self.may_discard():
            if self.dirty:
                self.load_team(self.active)
            event.accept()
        else:
            event.ignore()

    def reject(self):
        self.close()
