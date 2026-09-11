# 双向伤害首版验证 · 2026-09-11

## 2026-09-12：分配提示与阅读布局

伤害窗口增加列标题六项培养点提示、点击标题联动详情、可拖动高度分隔条、分段高对比详情、最大化／F11 全屏／Esc 恢复、80%–200% 表格与详情缩放。显示操作保留当前结果和选中情景，不重新触发计算。

相关回归：`tests/test_damage_ui.py tests/test_damage_workflow.py`，**18 passed，25.43 秒**。覆盖双向列标题的真实分配、标题点击、实际字号／行高变化、拖动后的区域大小、全屏恢复最大化及旧有自动计算生命周期。离屏查看应用样式截图 `artifacts/damage/resizable-detail.png`。本轮没有改动伤害公式或用户队伍数据库。


## 2026-09-12：自动计算、Mega／复制与队伍窗口

- 完整回归：`python -X utf8 -m pytest tests -q`，**162 passed，105.81 秒**。
- 最后补充“手选四招全为变化招式时不生成未知招式占位行”、普通复制选项自动重算等验证后，运行 `tests/test_damage_workflow.py tests/test_damage.py tests/test_damage_ui.py`，**37 passed，26.06 秒**。
- 实际用户队伍只读检查：沙奈朵带复制、沙奈朵进化石，四招为巨声／广域战力／戏法空间／守住；原拦截原因是复制结果未知。培养点保留 0/0/2/32/0/28，没有改写用户库。
- 计算测试：普通巨声对无特性耿鬼为 0；Mega 妖精皮肤巨声可命中，特攻实数 238。检查对应进化石、跨家族拒绝、保存数据不变、双向形态选择及切换时撤销旧结果。
- 窗口验证：900×600 下保存按钮完整可见；重命名在保存后生效；保存带复制配置出现成员级警告；自动重算不跳转设置页。
- 离屏使用程序样式和微软雅黑查看 `artifacts/damage/team-fixed-footer.png`、`artifacts/damage/mega-auto-comparison.png`。实际沙奈朵配置切换 Mega 后，对大狃拉零耐久巨声显示 109–129 HP；这是本地规则输出，不是 Switch 实机伤害验收。


最新招式矩阵与属性克制版：完整运行 `python -X utf8 -m pytest tests -q`，**157 passed，100.10 秒**。两个方向分页面、培养点／性格统计解析与升级、属性克制、窄屏排版及原队伍／识别／伤害回归均通过。离屏查看了四招页与常用招式页，截图为 `artifacts/damage/outgoing-comparison.png` 和 `artifacts/damage/incoming-comparison.png`；具体比较口径见 `docs/research/damage-comparison.md`。

后续预存队伍流程调整：伤害界面已改为直接选保存队伍／成员。原先的匹配前置条件和我方手工假设入口已撤除；以下首版记录保留为历史证据。新的 `test_damage_ui.py` 覆盖无当前阵容也可计算、保存后刷新、未保存草稿不参与、同物种跨队隔离、删除时不自动切换、修订／删除后的迟到结果丢弃、新截图保留预存选择并重置场况。匹配规则仍由 `test_teams.py` 单独验证。

此次相关回归：`tests/test_damage_ui.py tests/test_teams.py tests/test_damage.py tests/test_desktop.py`，**68 passed，19.24 秒**。伤害公式未变，本轮未重复 OCR／采集实机验收。

环境：Windows、`.venv-ui` Python 3.13.7、PySide6、Node.js 22.20.0。规则版本与独立预期见 [damage-rules.md](../research/damage-rules.md)。

## 自动验证

- 完整回归：`python -X utf8 -m pytest tests -q`，**140 passed，81.52 秒**。
- 随后补充主窗口联动用例，再运行 `tests/test_damage_ui.py`：**6 passed，2.62 秒**。这六项中五项已经包含在前述完整回归内。
- 伤害数值文件包含 21 项用例，覆盖物理／特殊双向、天气、灼伤、双打群攻、单目标双打墙、生命宝珠、能力等级、帮助、要害、守住、固定伤害、Mega 属性、六只截图能力值、逐情景 HP 分母及未知／不支持边界。
- 界面用例覆盖真实本地引擎结果、整队失配撤销、异步迟到结果、采用率快照变化、当前宝可梦更换、会话重置，以及主窗口切到未知目标／新截图。

## 人工查看

使用应用相同的样式和微软雅黑字体进行离屏界面验证。填写烈咬陆鲨四招，对巨金怪的三个假设情景执行双向计算，共 36 行：每情景四个我方招式、八个对手候选招式。变化／不支持项单独显示原因。确认结果表、来源／赛季说明和可滚动的配置详情可读。

本地产物（artifacts 不纳入源码）：

- `artifacts/damage/config.png`
- `artifacts/damage/results.png`

本次不需要真实 OBS 重新连接；主窗口调用链通过模拟采集结果验证。也未进行真实 Switch 单次伤害逐机制实测或 OP.GG 计算器交叉核对，这些属于后续完善规则证据的工作。
