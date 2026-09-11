"""Independent opponent hypotheses and per-scenario bidirectional damage ranges."""
from copy import deepcopy
from html import escape
import sqlite3

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView, QGroupBox, QSplitter)

from ..damage import DamageService, RULE_VERSION, battle_defaults
from ..teams import STATS, blank_member
from ..data.moves import power_label, accuracy_label, move_tooltip
from ..data.storage import TYPE_NAMES
from .team_dialog import MemberEditor, select, value
from .matchups import MatchupLabel
from .dialog_layout import fit_dialog


class ScenarioMember(MemberEditor):
    def pokemon_changed(self):
        super().pokemon_changed()
        self.ability.addItem('无特性效果（仅为假设）', '__none__')


class BattleEditor(QWidget):
    def __init__(self, changed):
        super().__init__()
        layout = QGridLayout(self)
        self.hp = QSpinBox()
        self.hp.setRange(0, 999)
        self.hp.setSpecialValueText('满 HP（假设）')
        self.status = QComboBox()
        for name, key in [('无异常',''), ('灼伤','brn'), ('麻痹','par'), ('中毒','psn'), ('剧毒','tox'), ('睡眠','slp'), ('冰冻','frz')]:
            self.status.addItem(name, key)
        self.fainted = QSpinBox()
        self.fainted.setRange(0, 5)
        for col, (label, widget) in enumerate([('当前 HP',self.hp),('异常状态',self.status),('倒下同伴数',self.fainted)]):
            layout.addWidget(QLabel(label), 0, col)
            layout.addWidget(widget, 1, col)
        self.boosts = {}
        for i, (key, name) in enumerate(list(STATS.items())[1:]):
            box = QSpinBox(); box.setRange(-6,6)
            self.boosts[key] = box
            layout.addWidget(QLabel(name+'等级'), 2+i//3*2, i%3)
            layout.addWidget(box, 3+i//3*2, i%3)
            box.valueChanged.connect(changed)
        self.flags = {}
        for i, (key, label) in enumerate([('ability_on','条件特性生效／本次威吓'), ('reflect','反射壁'),
            ('light_screen','光墙'), ('protected','守住'), ('helping_hand','受到帮助'),
            ('friend_guard','同伴友情防守'), ('tailwind','顺风')]):
            box = QCheckBox(label);self.flags[key]=box
            layout.addWidget(box, 6+i//2, i%2)
            box.toggled.connect(changed)
        self.hp.valueChanged.connect(changed);self.status.currentIndexChanged.connect(changed)
        self.fainted.valueChanged.connect(changed)

    def read(self):
        return {'hp':self.hp.value(), 'status':self.status.currentData(), 'allies_fainted':self.fainted.value(),
                'boosts':{k:b.value() for k,b in self.boosts.items()}, **{k:b.isChecked() for k,b in self.flags.items()}}

    def reset(self):
        self.hp.setValue(0);self.status.setCurrentIndex(0);self.fainted.setValue(0)
        for box in self.boosts.values():box.setValue(0)
        for box in self.flags.values():box.setChecked(False)


class ScenarioPage(QWidget):
    def __init__(self, rules, changed, title):
        super().__init__()
        layout = QVBoxLayout(self)
        self.name = QLineEdit(title)
        layout.addWidget(self.name)
        self.editor = ScenarioMember(rules, changed)
        self.battle = BattleEditor(changed)
        layout.addWidget(self.editor)
        layout.addWidget(self.battle)
        self.name.textChanged.connect(changed)


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
    def __init__(self, catalog, list_teams, configure_team, parent=None):
        super().__init__(parent)
        self.service = DamageService(catalog)
        self.rules = self.service.rules
        self.list_teams = list_teams
        self.selected_team = None
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
        refresh=QPushButton('刷新队伍');refresh.clicked.connect(self.refresh_teams)
        for w in [QLabel('我方队伍'),self.saved_team,self.own_slot,QLabel('对手'),self.target,refresh,setup]:
            sources.addWidget(w,1 if isinstance(w,QComboBox) else 0)
        layout.addLayout(sources)
        self.team_note=QLabel();self.team_note.setWordWrap(True);layout.addWidget(self.team_note)
        summaries=QHBoxLayout()
        self.own_summary=QLabel();self.enemy_summary=QLabel()
        self.own_matchups=MatchupLabel();self.enemy_matchups=MatchupLabel()
        self.own_form=QComboBox();self.enemy_form=QComboBox()
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
            if summary is self.own_summary:box.addWidget(self.copied_ability)
            box.addWidget(summary);box.addWidget(matchups);summaries.addWidget(group,1)
        layout.addLayout(summaries)
        self.result_splitter=QSplitter(Qt.Orientation.Vertical)
        self.result_splitter.setChildrenCollapsible(False)
        self.result_splitter.setHandleWidth(10)
        self.result_splitter.setStyleSheet('QSplitter::handle:vertical {background:#c5d4df; margin:2px 0; border-radius:3px;} QSplitter::handle:vertical:hover {background:#148878;}')
        layout.addWidget(self.result_splitter,1)
        self.tabs=QTabWidget();self.result_splitter.addWidget(self.tabs)
        self.direction_tables={}
        for direction,title,note in [
            ('我方 → 对手','我方打对手 · 四个招式','每行一个我方招式。零耐久不使用减防性格；满物防、满特防分别考虑 HP、对应防御培养点与增益性格。每格保留独立随机范围。'),
            ('对手 → 我方','对手打我方 · 常用招式','按招式采用率查看威胁。比较零输出、满物攻、满特攻和常用分配；我方始终使用预存配置，范围以我方最大 HP 为分母。')]:
            page=QWidget();box=QVBoxLayout(page)
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
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body)
        config=QVBoxLayout(body);self.tabs.addTab(scroll,'场况与情景设置')
        self.notice=QLabel('默认无天气／场地、满 HP、能力等级 0、非要害；普通对手默认无特性效果、无道具，Mega 使用对应特性和进化石。比较仅代表这些条件下的单次命中伤害。')
        self.notice.setWordWrap(True);config.addWidget(self.notice)
        env=QHBoxLayout();self.weather=QComboBox();self.terrain=QComboBox();self.targets=QComboBox()
        for n,k in [('无天气',''),('晴天','Sun'),('下雨','Rain'),('沙暴','Sand'),('下雪','Snow')]:self.weather.addItem(n,k)
        for n,k in [('无场地',''),('电气场地','Electric'),('青草场地','Grassy'),('薄雾场地','Misty'),('精神场地','Psychic')]:self.terrain.addItem(n,k)
        self.targets.addItem('群攻至少两个有效目标',2);self.targets.addItem('群攻只有一个有效目标',1)
        self.critical=QCheckBox('要害')
        for w in [self.weather,self.terrain,self.targets,self.critical]:env.addWidget(w)
        config.addLayout(env)
        self.common=QCheckBox('对手使用双打采用率前八个伤害招式（取消后使用各情景四招中的伤害招式）');self.common.setChecked(True)
        config.addWidget(self.common)
        explanation=QLabel('常用分配采用率仅描述六项培养点，不代表性格／特性／道具的联合概率。常用分配默认搭配采用率最高的性格作为假设；可在此修改。天气／场地需要手选；已计入能力等级的威吓不要重复勾选。')
        explanation.setWordWrap(True);config.addWidget(explanation)
        columns=QHBoxLayout();config.addLayout(columns)
        own=QWidget();own_layout=QVBoxLayout(own);own_layout.addWidget(QLabel('我方已保存配置及当前场况'))
        self.own=MemberEditor(self.rules,self.invalidate);self.own.setEnabled(False)
        self.own_battle=BattleEditor(self.invalidate)
        self.own.pokemon.currentIndexChanged.connect(self.own_battle.reset)
        own_layout.addWidget(self.own);own_layout.addWidget(self.own_battle);columns.addWidget(own,1)
        enemy=QWidget();enemy_layout=QVBoxLayout(enemy)
        self.scenarios=QTabWidget();self.scenarios.setUsesScrollButtons(True);enemy_layout.addWidget(self.scenarios)
        buttons=QHBoxLayout();reset=QPushButton('恢复默认比较情景');reset.clicked.connect(self.reset_scenarios)
        buttons.addWidget(reset);enemy_layout.addLayout(buttons);columns.addWidget(enemy,1)
        detail_panel=QWidget();detail_layout=QVBoxLayout(detail_panel);detail_layout.setContentsMargins(0,0,0,0)
        detail_tools=QHBoxLayout()
        detail_tools.addWidget(QLabel('计算详情 · 拖动上方分隔条调整高度'),1)
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
        self.result_splitter.addWidget(detail_panel)
        self.result_splitter.setStretchFactor(0,3);self.result_splitter.setStretchFactor(1,2)
        self.result_splitter.setSizes([390,260])
        self.result_splitter.handle(1).setToolTip('上下拖动，调整表格与详情的高度')
        self.zoom.currentIndexChanged.connect(self.apply_view_zoom)
        self.fullscreen_shortcut=QShortcut(QKeySequence('F11'),self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self.apply_view_zoom()
        footer=QHBoxLayout();self.status=QLabel('选择队伍与对手后计算。');self.status.setWordWrap(True)
        footer.addWidget(self.status,1);layout.addLayout(footer)
        self.own_form.currentIndexChanged.connect(self.form_changed)
        self.copied_ability.currentTextChanged.connect(self.form_changed)
        self.enemy_form.currentIndexChanged.connect(self.enemy_form_changed)
        self.saved_team.currentIndexChanged.connect(self.team_changed)
        self.own_slot.currentIndexChanged.connect(self.refresh_own)
        self.target.currentIndexChanged.connect(self.reset_scenarios)
        self.target.editTextChanged.connect(self.target_edited)
        self.common.toggled.connect(self.invalidate)
        for w in (self.weather,self.terrain,self.targets):w.currentIndexChanged.connect(self.invalidate)
        self.critical.toggled.connect(self.invalidate)
        self.tabs.currentChanged.connect(self.direction_changed)
        self.loading=False;self.refresh_teams();self.refresh_summaries()

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
        for table in self.direction_tables.values():
            table.setStyleSheet(f'QTableWidget {{font-size:{pixels}px; color:#172d43;}} QHeaderView::section {{font-size:{pixels}px; color:#27465b;}}')
            table.horizontalHeader().setMinimumSectionSize(round(150*scale))
            for row in range(table.rowCount()):table.setRowHeight(row,round(76*scale))
        self.detail.setStyleSheet(f'QTextEdit {{font-size:{pixels}px; color:#172d43; background:#ffffff; border:1px solid #bacbd7; border-radius:6px;}}')

    def select_scenario_column(self,table,col):
        if col>0 and table.rowCount():
            row=max(0,table.currentRow())
            table.setCurrentCell(row,col)
            self.show_comparison_detail(table,row,col)

    def refresh_summaries(self):
        slot=self.own_slot.currentData()
        member=self.selected_team['members'][slot] if self.selected_team and slot is not None else None
        if member:
            try:member=self.service.battle_form(member,self.own_form.currentData() or member['identity'])
            except ValueError:pass
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
        try:record=self.rules.record(value(self.target))
        except ValueError:record=None
        self.enemy_summary.setText(self.service.catalog.display_name(record)+' · '+' / '.join(TYPE_NAMES[t] for t in record['types']) if record else '请选择对手')
        self.enemy_matchups.show_types(record['types'] if record else [])

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
        select(self.target,self.enemy_form.currentData())

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
        try:record=self.rules.record(value(self.target))
        except ValueError:record=None
        usage=(self.service.catalog.usage or {}).get('pokemon',{}).get(record.get('opgg_key'),{}) if record else {}
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
        if not self.closing and self.isVisible():self.auto_timer.start()

    def refresh_teams(self):
        self.invalidate()
        selected=self.saved_team.currentData()
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
        self.loading=True
        select(self.target,self.rules.identity(record) if record else None)
        self.loading=False;self.reset_scenarios()

    def reset_scenarios(self):
        self.invalidate()
        self.loading=True
        for page in self.pages:page.deleteLater()
        self.pages=[];self.scenarios.clear()
        record=self.rules.record(self.target.currentData())
        self.fill_forms(self.enemy_form,record)
        usage=(self.service.catalog.usage or {}).get('pokemon',{}).get(record.get('opgg_key'),{}) if record else {}
        self.training_version=deepcopy((usage.get('training',[]),usage.get('natures',[])))
        if record:
            for preset in self.service.comparison_presets(record):self._add(preset)
        self.loading=False;self.refresh_summaries()

    def _add(self,preset):
        page=ScenarioPage(self.rules,self.invalidate,preset['name'])
        page.editor.load(preset['member']);page.editor.pokemon.setEnabled(False)
        page.direction=preset.get('direction');page.spread_usage=preset.get('spread_usage')
        page.original_points=deepcopy(preset['member']['points'])
        page.original_member=deepcopy(preset['member'])
        self.pages.append(page);self.scenarios.addTab(page,('攻 · ' if page.direction=='我方 → 对手' else '守 · ')+preset['name'])

    def snapshot(self):
        identity=value(self.target)
        if not identity or not self.pages:raise ValueError('请选择对手或明确的形态情景')
        slot=self.own_slot.currentData()
        if not self.selected_team or slot is None:raise ValueError('请先选择预存队伍和成员')
        try:
            current=next((t for t in self.list_teams() if t['id']==self.selected_team['id']),None)
        except (OSError,sqlite3.Error) as exc:raise ValueError('预存队伍读取失败，请刷新队伍') from exc
        if current!=self.selected_team:raise ValueError('预存队伍已更新或删除，请刷新队伍后重新计算')
        own=self.service.battle_form(current['members'][slot],self.own_form.currentData())
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
        usage=(self.service.catalog.usage or {}).get('pokemon',{}).get(record.get('opgg_key'))
        if ((usage or {}).get('training',[]),(usage or {}).get('natures',[]))!=self.training_version:
            raise ValueError('培养点统计已更新，请恢复默认比较情景后重新计算')
        own_battle=self.own_battle.read()
        if own['ability']=='trace':own_battle['copied_ability']=value(self.copied_ability)
        return {'own':own,'own_battle':own_battle,'scenarios':scenarios,'environment':env,
                'common':self.common.isChecked(),'team':deepcopy(current),'own_slot':slot,'source':'saved',
                'usage':deepcopy(usage),'usage_notice':self.service.catalog.learnset(record)[2],
                'dataset':self.service.catalog.bundle_id,'rules':RULE_VERSION}

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
        self.results_note.setText(f"预存队伍「{self.last_request['team']['name']}」 · 普通对手默认无特性效果／无道具；Mega 默认对应特性／进化石。每格独立随机范围。\n{self.last_request['usage_notice']}")
        self.status.setText('计算完成。点击格子查看条件；可到“场况与情景设置”调整。')
        self.direction_changed()

    def direction_changed(self,*_):
        if self.tabs.currentIndex()==2:self.detail.clear();return
        table=self.table if self.tabs.currentIndex()==0 else self.incoming_table
        if table.rowCount() and table.columnCount()>1:
            row=max(0,table.currentRow());col=max(1,table.currentColumn())
            table.setCurrentCell(row,col);self.show_comparison_detail(table,row,col)

    def render_comparison(self,table,direction):
        selected=[(i,r) for i,r in enumerate(self.rows) if r['direction']==direction]
        scene_ids=list(dict.fromkeys(r['scenario_index'] for _,r in selected))
        if direction=='我方 → 对手':keys=self.last_request['own']['moves']
        else:keys=list(dict.fromkeys(r['move']['key'] if r['move'] else None for _,r in selected))
        labels=['招式 · 原始属性\n威力 / 命中']
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
            name=f"{move['name']} · {TYPE_NAMES[move['type']]}\n{power_label(move)} / {accuracy_label(move)}" if move else '未填写招式'
            if direction=='对手 → 我方' and move:
                rate=(self.last_request['usage'] or {}).get('moves',{}).get(key)
                if rate is not None:name+=f' · 采用率 {rate:g}%'
            title=QTableWidgetItem(name)
            if move:title.setToolTip(move_tooltip(move))
            table.setItem(row,0,title);table.setRowHeight(row,round(76*self.zoom.currentData()/100))
            for col,scene_id in enumerate(scene_ids,1):
                found=next(((i,r) for i,r in selected if r['scenario_index']==scene_id and (r['move']['key'] if r['move'] else None)==key),None)
                if not found:table.setItem(row,col,QTableWidgetItem('—'));continue
                index,r=found
                text=(f"{r['percent_min']:.1f}–{r['percent_max']:.1f}%\n{r['minimum']}–{r['maximum']} HP" if r['status']=='ok'
                      else '变化招式\n无直接伤害' if r['status']=='status_move' else '⚠ 暂不可计算')
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
            flags={'ability_on':'条件特性生效／本次威吓','reflect':'反射壁','light_screen':'光墙','protected':'守住',
                   'helping_hand':'帮助','friend_guard':'友情防守','tailwind':'顺风'}
            active='、'.join(label for k,label in flags.items() if b[k]) or '无额外场况效果'
            if 'copied_ability' in b:
                copied=b['copied_ability']
                active+='；复制：'+('未触发／无效果（假设）' if copied=='__none__' else self.rules.options['abilities'].get(copied,{}).get('name','待确认'))
            boosts=' / '.join(f'{STATS[k]} {v:+d}' for k,v in b['boosts'].items())
            statuses={'':'无异常','brn':'灼伤','par':'麻痹','psn':'中毒','tox':'剧毒','slp':'睡眠','frz':'冰冻'}
            return f"当前 HP：{b['hp'] or '满 HP（假设）'}；{statuses[b['status']]}；倒下同伴 {b['allies_fainted']}\n能力等级：{boosts}\n{active}"
        env=self.last_request['environment']
        weather={'':'无天气','Sun':'晴天','Rain':'下雨','Sand':'沙暴','Snow':'下雪'}[env['weather']]
        terrain={'':'无场地','Psychic':'精神场地','Grassy':'青草场地','Electric':'电气场地','Misty':'薄雾场地'}[env['terrain']]
        move=r['move'];metrics=f"威力 {power_label(move)} · 命中 {accuracy_label(move)}" if move else ''
        def text(value):return escape(str(value)).replace('\n','<br>')
        result=(f"{r['percent_min']:.1f}–{r['percent_max']:.1f}% · {r['minimum']}–{r['maximum']} HP"
                if r['status']=='ok' else r.get('reason','无直接伤害'))
        section=lambda title,body:f'<h3 style="color:#146e65; margin-top:16px; margin-bottom:8px">{text(title)}</h3><p style="line-height:145%">{text(body)}</p>'
        self.detail.setHtml(
            f'<h2 style="margin-top:0">{text(move["name"] if move else "未填写招式")} · {text(r["direction"])}</h2>'
            f'<p style="color:#146e65; font-size:large"><b>{text(result)}</b></p>'
            f'<p>{text(r["scenario"])} · {text(metrics)}<br>{text(move.get("description","") if move else "")}</p>'
            +section('对手配置（本列假设）',build(r['enemy'])+'\n'+battle(r['enemy_battle']))
            +section('我方配置',build(self.last_request['own'])+'\n'+battle(self.last_request['own_battle']))
            +section('场况',f"{weather} · {terrain} · 有效目标 {env['targets']} · {'要害' if env['critical'] else '非要害'}\n目标当前／最大 HP：{r.get('current_hp','—')} / {r.get('max_hp','—')}")
            +section('独立随机结果',r.get('rolls','未计算'))
            +'<p>仅表示本次直接伤害，不包含命中率、追加效果、回复、反伤或下一回合。</p>')

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
