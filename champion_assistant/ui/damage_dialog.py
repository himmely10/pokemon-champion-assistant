"""Independent opponent hypotheses and per-scenario bidirectional damage ranges."""
from copy import deepcopy
from html import escape
import sqlite3

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView, QGroupBox, QSizePolicy,
    QButtonGroup, QRadioButton)

from ..damage import DamageService, RULE_VERSION, battle_defaults
from ..battle_effects import SUPPORT_EFFECTS, effect_summary
from ..ability_conditions import (ABILITY_TRIGGER_LABELS, ABILITY_SCENE_REQUIREMENTS,
                                  ABILITY_HP_REQUIREMENTS)
from ..teams import STATS, blank_member
from ..data.moves import power_label, accuracy_label, move_tooltip
from ..data.storage import TYPE_NAMES
from .team_dialog import MemberEditor, select, value
from .matchups import MatchupLabel
from .dialog_layout import fit_dialog


PREFERRED_OPPONENT_ABILITIES = {
    # The current Champions doubles data has no ability usage percentages.
    # Use the defining competitive ability as the visible default while still
    # leaving every legal ability available in the selector.
    'whimsicott': 'prankster',
}


def configure_ability_trigger(box, ability, prefix=''):
    label=ABILITY_TRIGGER_LABELS.get(ability)
    box.blockSignals(True)
    if box.property('abilityKey') != ability or not label:
        box.setChecked(False)
    box.setProperty('abilityKey', ability)
    box.setText((prefix+' · ' if prefix else '')+(label or '当前特性无需手动触发'))
    box.setVisible(bool(label))
    box.setEnabled(bool(label))
    box.blockSignals(False)


class ScenarioMember(MemberEditor):
    def pokemon_changed(self):
        super().pokemon_changed()
        self.ability.addItem('无特性效果（仅为假设）', '__none__')


class BattleEditor(QWidget):
    def __init__(self, changed):
        super().__init__()
        layout = QGridLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setVerticalSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.hp = QSpinBox()
        self.hp.setRange(1, 100)
        self.hp.setValue(100)
        self.hp.setSuffix('%')
        self.status = QComboBox()
        for name, key in [('无异常',''), ('灼伤','brn'), ('麻痹','par'), ('中毒','psn'), ('剧毒','tox'), ('睡眠','slp'), ('冰冻','frz')]:
            self.status.addItem(name, key)
        self.fainted = QSpinBox()
        self.fainted.setRange(0, 5)
        for col, (label, widget) in enumerate([('当前 HP',self.hp),('异常状态',self.status),('倒下同伴数',self.fainted)]):
            layout.addWidget(QLabel(label), 0, col)
            layout.addWidget(widget, 1, col)
        self.boosts = {}
        self.boost_labels = {}
        for i, (key, name) in enumerate(list(STATS.items())[1:]):
            box = QSpinBox(); box.setRange(-6,6)
            self.boosts[key] = box
            label=QLabel(name+'等级');self.boost_labels[key]=label
            layout.addWidget(label, 2+i//3*2, i%3)
            layout.addWidget(box, 3+i//3*2, i%3)
            box.valueChanged.connect(changed)
        self.flags = {}
        charge=QCheckBox('电光束：特攻等级已含本次充能 +1');self.flags['charge_boost_included']=charge
        layout.addWidget(charge,11,0,1,3);charge.toggled.connect(changed)
        ability=QCheckBox('条件特性生效／本次威吓');self.flags['ability_on']=ability
        layout.addWidget(ability,6,0,1,3);ability.toggled.connect(changed)
        self.groups={}
        for row, group in enumerate(('进攻辅助','防守保护','速度条件'),7):
            panel=QGroupBox(group+' · 此方');grid=QGridLayout(panel)
            self.groups[group]=panel
            for i,(key,_,label,_,tip) in enumerate(e for e in SUPPORT_EFFECTS if e[3]==group):
                box=QCheckBox(label);box.setToolTip(tip);self.flags[key]=box
                grid.addWidget(box,i//2,i%2);box.toggled.connect(changed)
            layout.addWidget(panel,row,0,1,3)
        note=QLabel('勾选表示当前场况已存在，是否对本招适用请查看伤害详情。\n携带辅助招式不会自动生效；双方分别设置，切换攻击方向时按作用方计算。')
        note.setWordWrap(True);layout.addWidget(note,10,0,1,3)
        self.hp.valueChanged.connect(changed);self.status.currentIndexChanged.connect(changed)
        self.fainted.valueChanged.connect(changed)

    def read(self):
        return {'hp':self.hp.value(), 'status':self.status.currentData(), 'allies_fainted':self.fainted.value(),
                'boosts':{k:b.value() for k,b in self.boosts.items()}, **{k:b.isChecked() for k,b in self.flags.items()}}

    def reset(self):
        self.hp.setValue(100);self.status.setCurrentIndex(0);self.fainted.setValue(0)
        for box in self.boosts.values():box.setValue(0)
        for box in self.flags.values():box.setChecked(False)


class ScenarioPage(QWidget):
    def __init__(self, rules, changed, title):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.name = QLineEdit(title)
        layout.addWidget(self.name)
        self.editor = ScenarioMember(rules, changed)
        self.battle = BattleEditor(changed)
        layout.addWidget(self.editor)
        layout.addWidget(self.battle)
        self.name.textChanged.connect(changed)
        self.editor.ability.currentIndexChanged.connect(self.refresh_ability_trigger)
        self.refresh_ability_trigger()

    def refresh_ability_trigger(self, *_):
        configure_ability_trigger(self.battle.flags['ability_on'], self.editor.ability.currentData())


class DamageWorker(QThread):
    def __init__(self, service, jobs, revision, parent=None):
        super().__init__(parent)
        self.service, self.jobs, self.revision = service, jobs, revision
        self.output, self.error = None, ''

    def run(self):
        try:
            self.output = self.service.execute(self.jobs)
        except Exception as exc:
            self.error = str(exc)


class DamageDialog(QDialog):
    correctionRequested = Signal(int)

    def __init__(self, catalog, list_teams, configure_team, parent=None, *, team_id=None, opponents=None):
        super().__init__(parent)
        self.service = DamageService(catalog)
        self.speed_service = DamageService(catalog)
        self.speed_cache = {}
        self.rules = self.service.rules
        self.list_teams = list_teams
        self.selected_team = None
        self.initial_team_id = team_id
        self.restricted_targets = opponents is not None
        self.loading = True
        self.revision = 0
        self.worker = None
        self.closing = False
        self.rows = []
        self.last_request = None
        self.pages = []
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.setInterval(350)
        self.auto_timer.timeout.connect(self.auto_calculate)
        self.setWindowTitle('伤害对照 · 我方四招与对手威胁')
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setSizeGripEnabled(True)
        self.previous_window_state = Qt.WindowState.WindowNoState
        fit_dialog(self, 1380, 950)
        layout=QVBoxLayout(self)
        sources=QHBoxLayout()
        self.saved_team=QComboBox();self.own_slot=QComboBox()
        from .team_dialog import combo
        self.target=combo(self.rules.choices(),'请选择对手')
        setup=QPushButton('管理队伍');setup.clicked.connect(configure_team)
        self.correct_target=QPushButton('修正对手槽位')
        self.correct_target.clicked.connect(lambda:self.correctionRequested.emit(self.target.currentIndex()))
        self.correct_target.setVisible(self.restricted_targets)
        refresh=QPushButton('刷新队伍');refresh.clicked.connect(self.refresh_teams)
        for w in [QLabel('我方队伍'),self.saved_team,self.own_slot,QLabel('对手'),self.target,self.correct_target,refresh,setup]:
            sources.addWidget(w,1 if isinstance(w,QComboBox) else 0)
        layout.addLayout(sources)
        self.team_note=QLabel();self.team_note.setWordWrap(True);layout.addWidget(self.team_note)
        summaries=QHBoxLayout()
        self.own_summary=QLabel();self.enemy_summary=QLabel()
        self.own_matchups=MatchupLabel();self.enemy_matchups=MatchupLabel()
        self.own_form=QComboBox();self.enemy_form=QComboBox()
        self.enemy_ability_choice=QComboBox()
        self.enemy_ability_buttons_widget=QWidget()
        self.enemy_ability_buttons_layout=QHBoxLayout(self.enemy_ability_buttons_widget)
        self.enemy_ability_buttons_layout.setContentsMargins(0,0,0,0)
        self.enemy_ability_buttons_layout.setSpacing(10)
        self.enemy_ability_button_group=QButtonGroup(self)
        self.enemy_ability_button_group.setExclusive(True)
        self.enemy_ability_buttons={}
        self.enemy_ability_note=QLabel();self.enemy_ability_note.setWordWrap(True)
        self.copied_ability=combo([
            ('未触发复制／无特性效果（假设）','__none__')]+[
            (v['name'],k) for k,v in self.rules.options['abilities'].items()
            if k not in {'trace','receiver','power-of-alchemy','protean','libero','color-change','imposter'}],
            '复制到的特性：请确认')
        self.copied_ability.setVisible(False)
        for title,summary,matchups in [('我方 · 本次计算形态',self.own_summary,self.own_matchups),('对手 · 当前形态',self.enemy_summary,self.enemy_matchups)]:
            group=QGroupBox(title);box=QVBoxLayout(group)
            summary.setWordWrap(True);summary.setTextFormat(Qt.TextFormat.PlainText)
            form=self.own_form if summary is self.own_summary else self.enemy_form
            box.addWidget(form)
            if summary is self.own_summary:
                box.addWidget(self.copied_ability)
                self.form_warning=QLabel();self.form_warning.setStyleSheet('color:#b33d14;font-weight:bold');self.form_warning.setWordWrap(True);box.addWidget(self.form_warning)
                edit_item=QPushButton('修改预存道具');edit_item.clicked.connect(configure_team);box.addWidget(edit_item)
            else:
                box.addWidget(self.enemy_ability_choice)
                box.addWidget(self.enemy_ability_buttons_widget)
                box.addWidget(self.enemy_ability_note)
            box.addWidget(summary);box.addWidget(matchups);summaries.addWidget(group,1)
        layout.addLayout(summaries)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.direction_tables={}
        for direction,title,note in [
            ('我方 → 对手','我方打对手 · 四个招式','每行一个我方招式。零耐久不使用减防性格；满物防、满特防分别考虑 HP、对应防御培养点与增益性格。每格保留独立随机范围。'),
            ('对手 → 我方','对手打我方 · 常用招式','按招式采用率查看威胁。比较零输出、满物攻、满特攻和常用分配；我方始终使用预存配置，范围以我方最大 HP 为分母。')]:
            page=QWidget();page.setObjectName('DialogPage');box=QVBoxLayout(page)
            hint=QLabel(note);hint.setWordWrap(True);box.addWidget(hint)
            table=QTableWidget(0,1);table.setHorizontalHeaderLabels(['招式'])
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setWordWrap(True);table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            table.horizontalHeader().setMinimumSectionSize(125)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionsClickable(True)
            table.horizontalHeader().sectionClicked.connect(lambda col,t=table:self.select_scenario_column(t,col))
            table.currentCellChanged.connect(lambda r,c,_r,_c,t=table:self.show_comparison_detail(t,r,c))
            box.addWidget(table,1);self.tabs.addTab(page,title);self.direction_tables[direction]=table
        self.table=self.direction_tables['我方 → 对手'];self.incoming_table=self.direction_tables['对手 → 我方']
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();body.setObjectName('DialogViewport');scroll.setWidget(body)
        config=QVBoxLayout(body);config.setAlignment(Qt.AlignmentFlag.AlignTop);self.tabs.addTab(scroll,'高级情景设置')
        self.notice=QLabel('默认无天气／场地、满 HP、能力等级 0、非要害；普通对手可统一选择特性假设，默认无特性效果、无道具；Mega 使用固定特性和对应进化石。比较仅代表这些条件下的单次命中伤害。')
        self.notice.setWordWrap(True);config.addWidget(self.notice)
        self.weather=QComboBox();self.terrain=QComboBox();self.targets=QComboBox()
        for n,k in [('无天气',''),('晴天','Sun'),('下雨','Rain'),('沙暴','Sand'),('下雪','Snow')]:self.weather.addItem(n,k)
        for n,k in [('无场地',''),('电气场地','Electric'),('青草场地','Grassy'),('薄雾场地','Misty'),('精神场地','Psychic')]:self.terrain.addItem(n,k)
        self.targets.addItem('群攻至少两个有效目标',2);self.targets.addItem('群攻只有一个有效目标',1)
        self.critical=QCheckBox('要害')
        self.common=QCheckBox('对手采用率前八招');self.common.setChecked(True)
        self.common.setToolTip('勾选后使用双打采用率前八个伤害招式；取消后使用各情景四招中的伤害招式。')
        explanation=QLabel('这里用于调整单个耐久／输出情景的 HP、异常状态、性格、道具和培养点。常用分配采用率仅描述六项培养点，不代表性格／特性／道具的联合概率。')
        explanation.setWordWrap(True);config.addWidget(explanation)
        columns_widget=QWidget();columns_widget.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        columns=QHBoxLayout(columns_widget);columns.setContentsMargins(0,0,0,0);columns.setAlignment(Qt.AlignmentFlag.AlignTop)
        config.addWidget(columns_widget,0,Qt.AlignmentFlag.AlignTop)
        own=QWidget();own.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        own_layout=QVBoxLayout(own);own_layout.setAlignment(Qt.AlignmentFlag.AlignTop);own_layout.addWidget(QLabel('我方已保存配置及当前场况'))
        self.own=MemberEditor(self.rules,self.invalidate);self.own.setEnabled(False)
        self.own_battle=BattleEditor(self.invalidate)
        self.own.pokemon.currentIndexChanged.connect(self.own_battle.reset)
        own_layout.addWidget(self.own);self.own.hide();own_layout.addWidget(self.own_battle)
        columns.addWidget(own,1,Qt.AlignmentFlag.AlignTop)
        enemy=QWidget();enemy.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        enemy_layout=QVBoxLayout(enemy);enemy_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scenarios=QTabWidget();self.scenarios.setUsesScrollButtons(True)
        self.scenarios.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum);enemy_layout.addWidget(self.scenarios)
        buttons=QHBoxLayout();reset=QPushButton('恢复默认比较情景');reset.clicked.connect(self.reset_scenarios)
        buttons.addWidget(reset);enemy_layout.addLayout(buttons)
        columns.addWidget(enemy,1,Qt.AlignmentFlag.AlignTop)
        detail_panel=QWidget();detail_panel.setObjectName('DialogPage');self.detail_page=detail_panel
        detail_layout=QVBoxLayout(detail_panel);detail_layout.setContentsMargins(0,0,0,0)
        detail_tools=QHBoxLayout()
        detail_tools.addWidget(QLabel('计算详情 · 在结果表中选择伤害格后到此查看'),1)
        self.zoom=QComboBox()
        for percent in (80,100,125,150,175,200):self.zoom.addItem(f'{percent}%',percent)
        self.zoom.setCurrentIndex(1)
        detail_tools.addWidget(QLabel('表格 / 详情缩放'));detail_tools.addWidget(self.zoom)
        self.fullscreen_button=QPushButton('全屏 F11')
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        detail_tools.addWidget(self.fullscreen_button)
        detail_layout.addLayout(detail_tools)
        self.detail=QTextEdit();self.detail.setReadOnly(True);self.detail.setMinimumHeight(80)
        self.detail.document().setDocumentMargin(14)
        self.detail.setPlaceholderText('悬浮列标题查看六项培养点；点击列标题或伤害格，查看该情景的完整配置和结果。')
        detail_layout.addWidget(self.detail,1)
        self.results_note=QLabel('');self.results_note.setWordWrap(True);detail_layout.addWidget(self.results_note)
        self.tabs.addTab(detail_panel,'计算详情')
        self.zoom.currentIndexChanged.connect(self.apply_view_zoom)
        self.fullscreen_shortcut=QShortcut(QKeySequence('F11'),self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self.apply_view_zoom()
        footer=QHBoxLayout();self.status=QLabel('选择队伍与对手后计算。');self.status.setWordWrap(True)
        footer.addWidget(self.status,1);layout.addLayout(footer)
        self.own_form.currentIndexChanged.connect(self.form_changed)
        self.copied_ability.currentTextChanged.connect(self.form_changed)
        self.enemy_form.currentIndexChanged.connect(self.enemy_form_changed)
        self.enemy_ability_choice.currentIndexChanged.connect(self.enemy_ability_changed)
        self.saved_team.currentIndexChanged.connect(self.team_changed)
        self.own_slot.currentIndexChanged.connect(self.refresh_own)
        self.target.currentIndexChanged.connect(self.reset_scenarios)
        self.target.editTextChanged.connect(self.target_edited)
        self.common.toggled.connect(self.invalidate)
        self.weather.currentIndexChanged.connect(self.environment_changed)
        self.terrain.currentIndexChanged.connect(self.environment_changed)
        self.targets.currentIndexChanged.connect(self.invalidate)
        self.critical.toggled.connect(self.invalidate)
        self.tabs.currentChanged.connect(self.direction_changed)
        self.build_quick_controls(layout)
        self.loading=False;self.refresh_teams();self.refresh_summaries()
        if opponents is not None:self.set_opponents(opponents)

    def set_opponents(self, records, selected_slot=0):
        self.restricted_targets=True
        self.loading=True
        self.target.blockSignals(True);self.target.setEditable(False);self.target.clear()
        for slot in range(6):
            record=records[slot] if slot<len(records) else None
            self.target.addItem(f"第 {slot+1} 槽 · "+(self.rules.name(self.rules.identity(record)) if record else '未确认，请返回主界面修正'),self.rules.identity(record) if record else None)
        self.target.setCurrentIndex(max(0,min(5,selected_slot)))
        self.target.blockSignals(False);self.correct_target.show()
        self.loading=False;self.reset_scenarios()

    def own_combat_member(self, member):
        member=deepcopy(member)
        identity=self.own_form.currentData() or member['identity']
        if identity!=member['identity']:
            record=self.rules.record(identity)
            stone=record.get('mega_item')
            if not stone:raise ValueError('当前形态没有对应进化石资料')
            member['item']=stone
        return self.service.battle_form(member,identity)

    def build_quick_controls(self, outer):
        panel=QGroupBox('即时场况 · 修改后自动重算')
        self.quick_panel=panel
        grid=QGridLayout(panel);grid.setVerticalSpacing(5);self.enemy_boosts={}
        grid.addWidget(QLabel('全局'),0,0)
        grid.addWidget(self.weather,0,1);grid.addWidget(self.terrain,0,2)
        grid.addWidget(self.targets,0,3,1,3);grid.addWidget(self.critical,0,6)
        grid.addWidget(self.common,0,7,1,2)
        grid.addWidget(QLabel('我方'),2,0);grid.addWidget(QLabel('对手全部情景'),3,0)
        grid.addWidget(QLabel('当前 HP %'),1,1)
        grid.addWidget(self.own_battle.hp,2,1)
        self.own_battle.hp.setToolTip('按剩余 HP 百分比计算；100 表示满 HP，疾风之翼、多重鳞片等会据此自动判断。')
        self.own_battle.hp.valueChanged.connect(self.hp_condition_changed)
        self.enemy_hp=QSpinBox();self.enemy_hp.setRange(1,100);self.enemy_hp.setValue(100);self.enemy_hp.setSuffix('%')
        self.enemy_hp.setToolTip('按剩余 HP 百分比应用到各情景；100 表示各自的满 HP。')
        grid.addWidget(self.enemy_hp,3,1);self.enemy_hp.valueChanged.connect(self.apply_enemy_quick)
        self.enemy_hp.valueChanged.connect(self.hp_condition_changed)
        for col,(key,name) in enumerate(list(STATS.items())[1:],2):
            grid.addWidget(QLabel(name+'等级'),1,col)
            # A single control is moved here, so the saved battle input cannot diverge.
            grid.addWidget(self.own_battle.boosts[key],2,col)
            self.own_battle.boost_labels[key].hide()
            box=QSpinBox();box.setRange(-6,6);self.enemy_boosts[key]=box
            grid.addWidget(box,3,col);box.valueChanged.connect(self.apply_enemy_quick)
        grid.addWidget(self.own_battle.flags['tailwind'],2,7)
        self.own_battle.groups['速度条件'].hide()
        self.enemy_tailwind=QCheckBox('对手顺风');grid.addWidget(self.enemy_tailwind,3,7)
        self.enemy_tailwind.toggled.connect(self.apply_enemy_quick)
        self.enemy_ability=QCheckBox('对手条件特性生效');grid.addWidget(self.enemy_ability,3,8)
        self.enemy_ability.toggled.connect(self.apply_enemy_quick)
        self.enemy_ability.toggled.connect(lambda checked:self.condition_trigger_changed('enemy',checked))
        grid.addWidget(self.own_battle.flags['ability_on'],2,8)
        self.own_battle.flags['ability_on'].toggled.connect(lambda checked:self.condition_trigger_changed('own',checked))
        self.speed_summary=QLabel();self.speed_summary.setWordWrap(True);self.speed_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self.speed_summary,4,0,1,9)
        outer.insertWidget(3,panel)
        self.refresh_condition_controls()

    def refresh_condition_controls(self):
        slot=self.own_slot.currentData()
        member=self.selected_team['members'][slot] if self.selected_team and slot is not None else None
        if member:
            try:member=self.own_combat_member(member)
            except ValueError:pass
        configure_ability_trigger(self.own_battle.flags['ability_on'], member.get('ability') if member else None, '我方')
        key=self.enemy_ability_choice.currentData()
        if key in ABILITY_TRIGGER_LABELS:
            configure_ability_trigger(self.enemy_ability,key,'对手')
        else:
            try:record=self.rules.record(self.enemy_form.currentData() or value(self.target))
            except ValueError:record=None
            candidates=[ability for ability in (self.rules.ability_keys(self.rules.identity(record)) if record else [])
                        if ability in ABILITY_TRIGGER_LABELS]
            configure_ability_trigger(self.enemy_ability,None,'对手')
            if candidates:
                names=[self.rules.options['abilities'].get(ability,{}).get('name',ability) for ability in candidates]
                self.enemy_ability.setText('对手条件特性：请先在上方选择'+'／'.join(names))
                self.enemy_ability.setVisible(True)
        self.sync_condition_controls()

    def condition_ability(self, side):
        if side=='enemy':return self.enemy_ability_choice.currentData()
        slot=self.own_slot.currentData()
        if not self.selected_team or slot is None:return None
        try:return self.own_combat_member(self.selected_team['members'][slot]).get('ability')
        except ValueError:return self.selected_team['members'][slot].get('ability')

    def condition_trigger_changed(self, side, checked):
        if self.loading:return
        ability=self.condition_ability(side)
        requirement=ABILITY_SCENE_REQUIREMENTS.get(ability)
        if requirement:
            box=self.weather if requirement[0]=='weather' else self.terrain
            desired=requirement[1] if checked else ''
            if checked or box.currentData()==requirement[1]:select(box,desired)
        hp_requirement=ABILITY_HP_REQUIREMENTS.get(ability)
        hp_box=self.own_battle.hp if side=='own' else self.enemy_hp
        if checked and hp_requirement=='full':hp_box.setValue(100)
        self.sync_condition_controls();self.invalidate()

    def environment_changed(self,*_):
        if self.loading:return
        self.sync_condition_controls();self.invalidate()

    def hp_condition_changed(self,*_):
        if self.loading:return
        self.sync_condition_controls();self.invalidate()

    def sync_condition_controls(self):
        if not hasattr(self,'enemy_ability'):return
        for side,box in [('own',self.own_battle.flags['ability_on']),('enemy',self.enemy_ability)]:
            ability=self.condition_ability(side)
            requirement=ABILITY_SCENE_REQUIREMENTS.get(ability)
            hp_requirement=ABILITY_HP_REQUIREMENTS.get(ability)
            if requirement:
                selector=self.weather if requirement[0]=='weather' else self.terrain
                active=selector.currentData()==requirement[1]
            elif hp_requirement=='full':
                hp_box=self.own_battle.hp if side=='own' else self.enemy_hp
                active=hp_box.value()==100
            else:continue
            box.blockSignals(True);box.setChecked(active);box.blockSignals(False)
        checked=self.enemy_ability.isChecked()
        for page in self.pages:
            page.battle.flags['ability_on'].blockSignals(True)
            page.battle.flags['ability_on'].setChecked(checked)
            page.battle.flags['ability_on'].blockSignals(False)

    def apply_enemy_quick(self,*_):
        if self.loading:return
        self.loading=True
        for page in self.pages:
            page.battle.hp.setValue(self.enemy_hp.value())
            for key,box in self.enemy_boosts.items():page.battle.boosts[key].setValue(box.value())
            page.battle.flags['tailwind'].setChecked(self.enemy_tailwind.isChecked())
            page.battle.flags['ability_on'].setChecked(self.enemy_ability.isChecked())
        self.loading=False;self.invalidate()

    def refresh_speed(self):
        if not hasattr(self,'speed_summary'):return
        try:
            from ..speed import speed_lines, SPEED_TIERS
            slot=self.own_slot.currentData()
            if not self.selected_team or slot is None:raise ValueError('请先选择已保存队伍与成员')
            own=self.own_combat_member(self.selected_team['members'][slot])
            env={'weather':self.weather.currentData(),'terrain':self.terrain.currentData()}
            battle=self.own_battle.read()
            if own['ability']=='trace':battle['copied_ability']=value(self.copied_ability)
            key=repr((own,battle,env))
            if key not in self.speed_cache:self.speed_cache[key]=self.speed_service.speed(own,battle,env)
            result=self.speed_cache[key]
            if result['status']!='ok':raise ValueError(result.get('reason','我方速度配置未填写'))
            text=f"我方实配速度：{result['speed']}（原始 {result['raw_speed']}）"
            record=self.rules.record(self.enemy_form.currentData())
            if record and self.pages:
                member=self.pages[0].editor.read();state=self.pages[0].battle.read()
                refs=speed_lines(record['base_stats']['speed'],stage=state['boosts']['speed'],tailwind=state['tailwind'],ability=member['ability'],ability_on=state['ability_on'],status=state['status'],**env)
                text+='  |  对手参考：'+' · '.join(f"{tier[0]} {speed}" for tier,speed in zip(SPEED_TIERS,refs))
            self.speed_summary.setText(text)
            self.speed_summary.setToolTip('参考档位并非对手真实配置；特性采用首个情景，天气、状态与速度等级按当前场况。')
        except (ValueError,KeyError,ImportError) as exc:self.speed_summary.setText('速度待确认：'+str(exc))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.setWindowState(self.previous_window_state)
            self.fullscreen_button.setText('全屏 F11')
        else:
            self.previous_window_state=self.windowState()
            self.showFullScreen()
            self.fullscreen_button.setText('退出全屏 F11 / Esc')

    def apply_view_zoom(self,*_):
        scale=self.zoom.currentData()/100
        pixels=round(15*scale)
        dark=bool(getattr(self.parent(), 'dark_theme', False))
        text='#dbe4f0' if dark else '#172d43'
        header='#9fb0c5' if dark else '#27465b'
        background='#111d31' if dark else '#ffffff'
        border='#34465f' if dark else '#bacbd7'
        for table in self.direction_tables.values():
            table.setStyleSheet(f'QTableWidget {{font-size:{pixels}px; color:{text};}} QHeaderView::section {{font-size:{pixels}px; color:{header};}}')
            table.horizontalHeader().setMinimumSectionSize(round(150*scale))
            for row in range(table.rowCount()):table.setRowHeight(row,round(102*scale))
        self.detail.setStyleSheet(f'QTextEdit {{font-size:{pixels}px; color:{text}; background:{background}; border:1px solid {border}; border-radius:6px;}}')

    def select_scenario_column(self,table,col):
        if col>0 and table.rowCount():
            row=max(0,table.currentRow())
            table.setCurrentCell(row,col)
            self.show_comparison_detail(table,row,col)

    def refresh_summaries(self):
        slot=self.own_slot.currentData()
        member=self.selected_team['members'][slot] if self.selected_team and slot is not None else None
        if member:
            try:
                member=self.own_combat_member(member)
                selected_identity=self.own_form.currentData()
                saved_item=self.selected_team['members'][slot].get('item')
                temporary_item=member.get('item')
                if selected_identity!=self.selected_team['members'][slot]['identity'] and temporary_item!=saved_item:
                    item_name=self.rules.options['items'].get(temporary_item,{}).get('name',temporary_item)
                    self.form_warning.setText(f'本次计算自动采用{item_name}；预存队伍仍保留原道具。')
                else:self.form_warning.clear()
            except ValueError as exc:self.form_warning.setText('⚠ '+str(exc))
        self.copied_ability.setVisible(bool(member and member['ability']=='trace'))
        record=self.rules.record(member['identity']) if member else None
        self.own_matchups.show_types(record['types'] if record else [])
        if member:
            nature=self.rules.options['natures'].get(member['nature'],{}).get('name','未知性格')
            ability=self.rules.options['abilities'].get(member['ability'],{}).get('name','未知特性')
            item='无道具' if member['item']=='none' else self.rules.options['items'].get(member['item'],{}).get('name','未知道具')
            copied=self.copied_ability.currentText() if member['ability']=='trace' else ''
            self.own_summary.setText(f"{self.rules.name(member['identity'])} · {nature} · {ability} · {item}"+(f'\n{copied}' if copied else ''))
        else:self.own_summary.setText('请选择预存队伍和成员')
        self.refresh_speed()
        try:record=self.rules.record(self.enemy_form.currentData() or value(self.target))
        except ValueError:record=None
        self.enemy_summary.setText(self.service.catalog.display_name(record)+' · '+' / '.join(TYPE_NAMES[t] for t in record['types']) if record else '请选择对手')
        self.enemy_matchups.show_types(record['types'] if record else [])
        self.refresh_condition_controls()

    def fill_forms(self, box, record):
        box.blockSignals(True);box.clear()
        if record:
            for form in self.service.catalog.form_family(record):
                label=self.service.catalog.display_name(form)
                box.addItem('计算形态 · '+label,self.rules.identity(form))
            select(box,self.rules.identity(record))
        else:box.addItem('计算形态 · 请先选择宝可梦',None)
        box.blockSignals(False)

    def form_changed(self,*_):
        if self.loading:return
        self.invalidate();self.refresh_summaries()

    def enemy_form_changed(self,*_):
        if self.loading:return
        self.reset_scenarios(preserve_form=True)

    def configure_enemy_abilities(self, record):
        self.enemy_ability_choice.blockSignals(True)
        self.enemy_ability_choice.clear()
        abilities=self.rules.ability_keys(self.rules.identity(record)) if record else []
        fixed=bool(record and record.get('opgg_key','').startswith('mega-') and len(abilities)==1)
        if fixed:
            key=abilities[0]
            name=self.rules.options['abilities'].get(key,{}).get('name',key)
            self.enemy_ability_choice.addItem('固定特性 · '+name,key)
        else:
            self.enemy_ability_choice.addItem('特性假设 · 无特性效果','__none__')
            for key in abilities:
                name=self.rules.options['abilities'].get(key,{}).get('name',key)
                self.enemy_ability_choice.addItem('特性假设 · '+name,key)
            preferred=PREFERRED_OPPONENT_ABILITIES.get(record.get('opgg_key') or record.get('source_slug')) if record else None
            if preferred in abilities:select(self.enemy_ability_choice,preferred)
        self.enemy_ability_choice.setEnabled(bool(record) and not fixed)
        self.enemy_ability_choice.blockSignals(False)
        self.rebuild_enemy_ability_buttons(abilities,fixed)
        self.refresh_enemy_ability_note()

    def rebuild_enemy_ability_buttons(self, abilities, fixed):
        while self.enemy_ability_buttons_layout.count():
            item=self.enemy_ability_buttons_layout.takeAt(0)
            widget=item.widget()
            if widget:
                self.enemy_ability_button_group.removeButton(widget);widget.deleteLater()
        self.enemy_ability_buttons={}
        choices=[] if fixed else [('__none__','无特性效果')]+[
            (key,self.rules.options['abilities'].get(key,{}).get('name',key)) for key in abilities]
        for key,name in choices:
            button=QRadioButton(name)
            entry=self.rules.options['abilities'].get(key,{})
            if entry.get('description'):button.setToolTip(entry['description'])
            button.clicked.connect(lambda _checked,k=key:select(self.enemy_ability_choice,k))
            self.enemy_ability_button_group.addButton(button)
            self.enemy_ability_buttons_layout.addWidget(button)
            self.enemy_ability_buttons[key]=button
        self.enemy_ability_buttons_layout.addStretch(1)
        show_parallel=len(abilities)>1 and not fixed
        self.enemy_ability_buttons_widget.setVisible(show_parallel)
        self.enemy_ability_choice.setVisible(not show_parallel)
        selected=self.enemy_ability_buttons.get(self.enemy_ability_choice.currentData())
        if selected:selected.setChecked(True)

    def refresh_enemy_ability_note(self):
        key=self.enemy_ability_choice.currentData()
        if not key or key=='__none__':
            self.enemy_ability_note.setText('当前按无特性减伤／增伤计算。')
            if hasattr(self,'enemy_ability'):self.refresh_condition_controls()
            return
        entry=self.rules.options['abilities'].get(key,{})
        prefix='固定生效' if not self.enemy_ability_choice.isEnabled() else '当前假设'
        self.enemy_ability_note.setText(f"{prefix}：{entry.get('name',key)}。{entry.get('description','')}")
        if hasattr(self,'enemy_ability'):
            self.refresh_condition_controls()

    def enemy_ability_changed(self,*_):
        if self.loading:return
        self.loading=True
        key=self.enemy_ability_choice.currentData()
        selected=self.enemy_ability_buttons.get(key)
        if selected:selected.setChecked(True)
        for page in self.pages:select(page.editor.ability,key)
        self.loading=False
        self.refresh_enemy_ability_note();self.invalidate();self.refresh_summaries()

    def showEvent(self,event):
        super().showEvent(event)
        self.closing=False
        # Fullscreen/maximize also sends show events; preserve valid results and selection.
        if self.rows and self.last_request:
            try:
                if self.snapshot()==self.last_request:return
            except (ValueError,KeyError):pass
        self.auto_timer.start()

    def auto_calculate(self):
        if self.isVisible() and not self.closing and not self.worker:self.calculate()

    def target_edited(self):
        self.invalidate();self.refresh_summaries()

    def refresh_statistics(self):
        try:record=self.rules.record(self.enemy_form.currentData() or value(self.target))
        except ValueError:record=None
        usage=self.service.catalog.usage_for(record)[0] if record else None
        usage=usage or {}
        version=(usage.get('training',[]),usage.get('natures',[]))
        if record and version!=getattr(self,'training_version',None):
            self.reset_scenarios()
            self.status.setText('培养点／性格统计已更新，比较情景已恢复为新默认值，正在自动计算。')
        else:self.invalidate()

    def invalidate(self, *_):
        if self.loading:return
        self.revision+=1
        self.rows=[];self.last_request=None
        for table in self.direction_tables.values():table.setRowCount(0)
        self.detail.clear()
        self.results_note.clear()
        self.status.setText('输入已变化，正在准备自动计算…')
        self.refresh_speed()
        if not self.closing and self.isVisible():self.auto_timer.start()

    def refresh_teams(self):
        self.invalidate()
        selected=self.saved_team.currentData() or self.initial_team_id
        self.saved_team.blockSignals(True);self.saved_team.clear()
        self.saved_team.addItem('请选择预存队伍',None)
        error=''
        try:
            for team in self.list_teams():self.saved_team.addItem(team['name'],team['id'])
        except (ValueError,OSError,sqlite3.Error) as exc:
            error=f'预存队伍读取失败：{exc}'
        self.saved_team.setCurrentIndex(max(0,self.saved_team.findData(selected)))
        self.saved_team.blockSignals(False);self.team_changed()
        if error:self.team_note.setText(error)

    def team_changed(self):
        self.invalidate()
        self.selected_team=None
        try:
            self.selected_team=deepcopy(next((t for t in self.list_teams() if t['id']==self.saved_team.currentData()),None))
        except (ValueError,OSError,sqlite3.Error):pass
        selected=self.own_slot.currentData()
        self.own_slot.blockSignals(True);self.own_slot.clear()
        if self.selected_team:
            for slot,m in enumerate(self.selected_team['members']):
                self.own_slot.addItem(f"第 {slot+1} 槽 · {self.rules.name(m['identity'])}",slot)
            self.team_note.setText(f"按预存队伍「{self.selected_team['name']}」计算；我方培养配置只读，修改请到队伍管理保存。当前不进行我方识别或阵容匹配。")
        else:self.team_note.setText('请先选择预存队伍；还没有队伍时，点击“管理预存队伍”创建并保存。')
        self.own_slot.setCurrentIndex(max(0,self.own_slot.findData(selected)) if self.own_slot.count() else -1)
        self.own_slot.blockSignals(False);self.refresh_own()

    def refresh_own(self):
        self.invalidate()
        slot=self.own_slot.currentData()
        member=self.selected_team['members'][slot] if self.selected_team and slot is not None else None
        self.loading=True;self.own.load(member or blank_member())
        self.fill_forms(self.own_form,self.rules.record(member['identity']) if member else None)
        self.copied_ability.setCurrentIndex(0)
        self.loading=False
        self.own_battle.reset();self.refresh_summaries()

    def set_target(self, record):
        if self.restricted_targets:
            identity=self.rules.identity(record) if record else None
            index=self.target.findData(identity)
            if index>=0:self.target.setCurrentIndex(index)
            return
        self.loading=True
        select(self.target,self.rules.identity(record) if record else None)
        self.loading=False;self.reset_scenarios()

    def reset_scenarios(self,*_,preserve_form=False):
        self.invalidate()
        self.loading=True
        for page in self.pages:page.deleteLater()
        self.pages=[];self.scenarios.clear()
        record=self.rules.record(self.enemy_form.currentData() if preserve_form else self.target.currentData())
        if not preserve_form:self.fill_forms(self.enemy_form,record)
        self.configure_enemy_abilities(record)
        usage=self.service.catalog.usage_for(record)[0] if record else None
        usage=usage or {}
        self.training_version=deepcopy((usage.get('training',[]),usage.get('natures',[])))
        if record:
            for preset in self.service.comparison_presets(record):self._add(preset)
            ability=self.enemy_ability_choice.currentData()
            for page in self.pages:select(page.editor.ability,ability)
        self.loading=False;self.apply_enemy_quick();self.refresh_summaries()

    def _add(self,preset):
        page=ScenarioPage(self.rules,self.invalidate,preset['name'])
        page.editor.load(preset['member']);page.editor.pokemon.setEnabled(False)
        page.direction=preset.get('direction');page.spread_usage=preset.get('spread_usage')
        page.original_points=deepcopy(preset['member']['points'])
        page.original_member=deepcopy(preset['member'])
        self.pages.append(page);self.scenarios.addTab(page,('攻 · ' if page.direction=='我方 → 对手' else '守 · ')+preset['name'])

    def snapshot(self):
        identity=self.enemy_form.currentData()
        if not value(self.target) or not identity or not self.pages:raise ValueError('请选择对手或明确的形态情景')
        slot=self.own_slot.currentData()
        if not self.selected_team or slot is None:raise ValueError('请先选择预存队伍和成员')
        try:
            current=next((t for t in self.list_teams() if t['id']==self.selected_team['id']),None)
        except (OSError,sqlite3.Error) as exc:raise ValueError('预存队伍读取失败，请刷新队伍') from exc
        if current!=self.selected_team:raise ValueError('预存队伍已更新或删除，请刷新队伍后重新计算')
        own=self.own_combat_member(current['members'][slot])
        scenarios=[]
        for p in self.pages:
            member=p.editor.read()
            if not member or member['identity']!=identity:raise ValueError('情景与当前对手身份不同，请重新选择对手')
            name=p.name.text() or '未命名假设'
            if member!=p.original_member:name+='（已调整）'
            scenarios.append({'name':name, 'member':member,'battle':p.battle.read(),
                              'direction':p.direction,'spread_usage':p.spread_usage if member['points']==p.original_points else None})
        env={'weather':self.weather.currentData(),'terrain':self.terrain.currentData(),
             'targets':self.targets.currentData(),'critical':self.critical.isChecked()}
        record=self.rules.record(identity)
        usage,_=self.service.catalog.usage_for(record)
        move_rates,_,_=self.service.catalog.move_usage(record)
        if ((usage or {}).get('training',[]),(usage or {}).get('natures',[]))!=self.training_version:
            raise ValueError('培养点统计已更新，请恢复默认比较情景后重新计算')
        own_battle=self.own_battle.read()
        if own['ability']=='trace':own_battle['copied_ability']=value(self.copied_ability)
        return {'own':own,'own_battle':own_battle,'scenarios':scenarios,'environment':env,
                'common':self.common.isChecked(),'team':deepcopy(current),'own_slot':slot,'source':'saved',
                'usage':{**deepcopy(usage or {}),'moves':deepcopy(move_rates)},'usage_notice':self.service.catalog.learnset(record)[2],
                'dataset':self.service.catalog.bundle_id,'rules':RULE_VERSION,
                'snapshot_token':getattr(self.service.catalog,'snapshot_token',None)}

    def calculate(self):
        if self.worker:return
        self.invalidate()
        self.auto_timer.stop()
        try:
            request=self.snapshot()
            rows,jobs=self.service.jobs(request['own'],request['own_battle'],request['scenarios'],request['environment'],common=request['common'])
        except (ValueError,KeyError) as exc:
            self.status.setText(str(exc));return
        self.last_request=request;self.pending_rows=rows
        self.status.setText('正在逐情景计算两个方向…')
        self.worker=DamageWorker(self.service,jobs,self.revision,self)
        self.worker.finished.connect(self.finished_calculation);self.worker.start()

    def finished_calculation(self):
        worker=self.worker;self.worker=None
        worker.deleteLater()
        if self.closing:self.close();return
        if worker.revision!=self.revision:
            if self.isVisible():self.auto_timer.start()
            return
        try:
            if self.snapshot()!=self.last_request:
                self.invalidate();return
        except (ValueError,KeyError):self.invalidate();return
        if worker.error:self.status.setText(worker.error);return
        self.rows=[{**row,**result} for row,result in zip(self.pending_rows,worker.output)]
        for direction,table in self.direction_tables.items():self.render_comparison(table,direction)
        self.results_note.setText(f"预存队伍「{self.last_request['team']['name']}」 · 普通对手默认无特性效果，可在上方统一选择特性假设；Mega 固定使用对应特性／进化石。每格独立随机范围。\n{self.last_request['usage_notice']}")
        failures=list(dict.fromkeys(r.get('reason','未知原因') for r in self.rows if r['status']=='unavailable'))
        if failures:
            self.status.setText(f"计算完成，其中 {sum(r['status']=='unavailable' for r in self.rows)} 项暂不可计算。原因："+'；'.join(failures))
        else:
            self.status.setText('计算完成。点击格子查看条件；可到“高级情景设置”调整。')
        self.direction_changed()

    def direction_changed(self,*_):
        if self.tabs.currentIndex() not in (0,1):return
        table=self.table if self.tabs.currentIndex()==0 else self.incoming_table
        if table.rowCount() and table.columnCount()>1:
            row=max(0,table.currentRow());col=max(1,table.currentColumn())
            table.setCurrentCell(row,col);self.show_comparison_detail(table,row,col)

    def render_comparison(self,table,direction):
        selected=[(i,r) for i,r in enumerate(self.rows) if r['direction']==direction]
        scene_ids=list(dict.fromkeys(r['scenario_index'] for _,r in selected))
        if direction=='我方 → 对手':keys=self.last_request['own']['moves']
        else:keys=list(dict.fromkeys(r['move']['key'] if r['move'] else None for _,r in selected))
        labels=['招式 · 原始属性\n威力 / 命中 / 先制']
        for index in scene_ids:
            scene=self.last_request['scenarios'][index];rate=scene['spread_usage']
            nature=self.rules.options['natures'].get(scene['member']['nature'],{}).get('name','未知性格')
            labels.append(scene['name']+(f"\n分配采用率 {rate:g}%" if rate is not None else '')+f'\n{nature}（假设）')
        table.clear();table.setColumnCount(len(labels));table.setHorizontalHeaderLabels(labels);table.setRowCount(len(keys))
        for col,index in enumerate(scene_ids,1):
            scene=self.last_request['scenarios'][index]
            points='\n'.join(f"{label}：{scene['member']['points'].get(key) if scene['member']['points'].get(key) is not None else '未知'}" for key,label in STATS.items())
            nature=self.rules.options['natures'].get(scene['member']['nature'],{}).get('name','未知性格')
            tip=f"{scene['name']}\n{points}\n性格：{nature}（独立假设）"
            if scene['spread_usage'] is not None:tip+=f"\n培养点分配采用率：{scene['spread_usage']:g}%（不代表与性格的联合概率）"
            tip+='\n点击此列标题，在下方展开完整情景。'
            table.horizontalHeaderItem(col).setToolTip(tip)
        for row,key in enumerate(keys):
            move=self.service.catalog.moves.get(key)
            priority=move.get('priority') if move else None
            priority_label='未知' if priority is None else f'{priority:+d}'
            name=f"{move['name']} · {TYPE_NAMES[move['type']]}\n{power_label(move)} / {accuracy_label(move)} / 先制 {priority_label}" if move else '未填写招式'
            if direction=='对手 → 我方' and move:
                rate=(self.last_request['usage'] or {}).get('moves',{}).get(key)
                if rate is not None:name+=f' · 采用率 {rate:g}%'
            title=QTableWidgetItem(name)
            if move:title.setToolTip(move_tooltip(move))
            table.setItem(row,0,title);table.setRowHeight(row,round(102*self.zoom.currentData()/100))
            for col,scene_id in enumerate(scene_ids,1):
                found=next(((i,r) for i,r in selected if r['scenario_index']==scene_id and (r['move']['key'] if r['move'] else None)==key),None)
                if not found:table.setItem(row,col,QTableWidgetItem('—'));continue
                index,r=found
                chance=r.get('hit_chance',{});hit=chance.get('percent')
                metadata=[]
                if hit is not None:metadata.append(f"命中 {hit:g}%"+(' · '+'／'.join(chance['notes']) if chance.get('notes') else ''))
                priority=r.get('priority',{});current=priority.get('current')
                if current is not None:
                    note='／'.join(priority.get('notes',[]))
                    metadata.append(f"先制 {current:+d}"+(f' · {note}' if note else ''))
                meta_text=('\n'+' · '.join(metadata)) if metadata else ''
                status_reason=r.get('reason','变化招式：没有本次直接伤害范围')
                status_text=('变化招式\n无效：'+status_reason if '无效' in status_reason else '变化招式\n无直接伤害')
                text=(f"{r['percent_min']:.1f}–{r['percent_max']:.1f}%\n{r['minimum']}–{r['maximum']} HP"+meta_text if r['status']=='ok'
                      else status_text+meta_text if r['status']=='status_move'
                      else '⚠ 暂不可计算\n'+r.get('reason','未知原因'))
                item=QTableWidgetItem(text);item.setData(Qt.ItemDataRole.UserRole,index)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                scene=self.last_request['scenarios'][scene_id]
                nature=self.rules.options['natures'].get(scene['member']['nature'],{}).get('name','未知性格')
                points=' / '.join(f'{STATS[k]} {v}' for k,v in scene['member']['points'].items())
                item.setToolTip(f"{scene['name']} · 性格 {nature}\n{points}\n"+r.get('reason',r.get('note','')))
                table.setItem(row,col,item)

    def show_comparison_detail(self,table,row,col):
        if col==0:col=1
        item=table.item(row,col)
        if item is not None:
            index=item.data(Qt.ItemDataRole.UserRole)
            if index is not None:self.show_detail(index)

    def show_detail(self,row,*_):
        if row<0 or row>=len(self.rows) or not self.last_request:return
        r=self.rows[row]
        def build(member):
            opts=self.rules.options
            nature=opts['natures'].get(member['nature'],{}).get('name','未知')
            ability='无特性效果（假设）' if member['ability']=='__none__' else opts['abilities'].get(member['ability'],{}).get('name','未知')
            item='无道具' if member['item']=='none' else opts['items'].get(member['item'],{}).get('name','未知')
            points=' / '.join(f"{STATS[k]} {v if v is not None else '未知'}" for k,v in member['points'].items())
            return f"{self.rules.name(member['identity'])} · {nature} · {ability} · {item}\n培养点：{points}"
        def battle(b):
            flags={'ability_on':'条件特性生效／本次威吓', **{key:label for key,_,label,*_ in SUPPORT_EFFECTS}}
            active='已启用：'+('、'.join(label for k,label in flags.items() if b.get(k,False)) or '无额外场况效果')
            if 'copied_ability' in b:
                copied=b['copied_ability']
                active+='；复制：'+('未触发／无效果（假设）' if copied=='__none__' else self.rules.options['abilities'].get(copied,{}).get('name','待确认'))
            boosts=' / '.join(f'{STATS[k]} {v:+d}' for k,v in b['boosts'].items())
            statuses={'':'无异常','brn':'灼伤','par':'麻痹','psn':'中毒','tox':'剧毒','slp':'睡眠','frz':'冰冻'}
            return f"当前 HP：{b['hp']}%；{statuses[b['status']]}；倒下同伴 {b['allies_fainted']}\n能力等级：{boosts}\n{active}"
        env=self.last_request['environment']
        weather={'':'无天气','Sun':'晴天','Rain':'下雨','Sand':'沙暴','Snow':'下雪'}[env['weather']]
        terrain={'':'无场地','Psychic':'精神场地','Grassy':'青草场地','Electric':'电气场地','Misty':'薄雾场地'}[env['terrain']]
        move=r['move'];metrics=f"威力 {power_label(move)} · 原始命中 {accuracy_label(move)}" if move else ''
        chance=r.get('hit_chance',{});hit=chance.get('percent')
        if hit is not None:
            metrics+=f" · 实际命中 {hit:g}%"
            if chance.get('notes'):metrics+=' ('+' / '.join(chance['notes'])+')'
        priority=r.get('priority',{});original=priority.get('original');current=priority.get('current')
        if original is not None:
            metrics+=f' · 原始先制 {original:+d} · 当前先制 {current:+d}'
            if priority.get('notes'):metrics+=' ('+' / '.join(priority['notes'])+')'
        def text(value):return escape(str(value)).replace('\n','<br>')
        result=(f"{r['percent_min']:.1f}–{r['percent_max']:.1f}% · {r['minimum']}–{r['maximum']} HP"
                if r['status']=='ok' else r.get('reason','无直接伤害'))
        section=lambda title,body:f'<h3 style="color:#146e65; margin-top:16px; margin-bottom:8px">{text(title)}</h3><p style="line-height:145%">{text(body)}</p>'
        multi=r.get('multi_hit')
        multi_text=''
        if multi:
            multi_text='单段：'+result+'\n'+'\n'.join(f"{part['hits']} 次命中：{part['percent_min']:.1f}–{part['percent_max']:.1f}% · {part['minimum']}–{part['maximum']} HP" for part in multi.get('scenarios',[]) if part.get('status')=='ok')
        ability_text=''
        if r.get('details',{}).get('defenderAbility'):
            defender=self.last_request['own'] if r['direction']=='对手 → 我方' else r['enemy']
            key=defender.get('ability')
            name=self.rules.options['abilities'].get(key,{}).get('name',r['details']['defenderAbility'])
            ability_text=f'防守方特性“{name}”已计入本次伤害。'
        self.detail.setHtml(
            f'<h2 style="margin-top:0">{text(move["name"] if move else "未填写招式")} · {text(r["direction"])}</h2>'
            f'<p style="color:#146e65; font-size:large"><b>{text(result)}</b></p>'
            f'<p>{text(r["scenario"])} · {text(metrics)}<br>{text(move.get("description","") if move else "")}</p>'
            +section('对手配置（本列假设）',build(r['enemy'])+'\n'+battle(r['enemy_battle']))
            +section('我方配置',build(self.last_request['own'])+'\n'+battle(self.last_request['own_battle']))
            +section('场况',f"{weather} · {terrain} · 有效目标 {env['targets']} · {'要害' if env['critical'] else '非要害'}\n目标当前／最大 HP：{r.get('current_hp','—')} / {r.get('max_hp','—')}")
            +section('辅助效果 · 本招判定',effect_summary(r) if r['status']=='ok' else '本招无有效直接伤害结果；已启用的辅助条件未判定生效。')
            +(section('特性修正',ability_text) if ability_text else '')
            +(section('多次命中 · 独立次数情景',multi_text) if multi_text else '')
            +section('独立随机结果',r.get('rolls','未计算'))
            +section('资料版本',f"{self.last_request['dataset']} · {self.last_request['rules']}\n快照 {self.last_request.get('snapshot_token') or '独立资料视图'}")
            +'<p>伤害范围以招式命中为前提；实际命中率已计入当前可确定的天气与特性修正，不包含追加效果、回复、反伤或下一回合。</p>')

    def clear_session(self):
        self.invalidate();self.set_target(None)
        self.refresh_teams()
        self.own_battle.reset()
        self.weather.setCurrentIndex(0);self.terrain.setCurrentIndex(0)
        self.targets.setCurrentIndex(0);self.critical.setChecked(False)

    def closeEvent(self,event):
        self.closing=True
        self.auto_timer.stop()
        self.invalidate()
        if self.worker:
            self.closing=True;self.status.setText('正在结束本地计算…');event.ignore()
        else:event.accept()

    def reject(self):
        if self.isFullScreen():self.toggle_fullscreen()
        else:self.close()
