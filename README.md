# Pokemon Champion Assistant


**当前版本：v0.4.2 Windows 候选版。** [下载安装包](https://github.com/himmely10/pokemon-champion-assistant/releases/tag/v0.4.2) · [版本说明](docs/releases/v0.4.2.md) · [构建与发行](docs/release.md)

这是一个面向《宝可梦 Champions》对战的本地桌面助手。在同一个窗口中管理己方队伍、识别对手选队截图、比较双向伤害与速度线，并浏览本地宝可梦资料。网页界面通过仅监听 `127.0.0.1` 的本地 API 调用现有计算模块；它不是需要上传队伍或截图的在线服务。

Windows 用户可从 GitHub Releases 下载 `PokemonChampionAssistant-0.4.2-windows-x64-Setup.exe`，安装后从开始菜单打开 **Pokemon Champion Assistant**。安装包包含 Python、Node.js、Qt、OCR 模型和离线资料，无需另外准备开发环境。安装包 SHA-256：`BA7A56A3DF3C0DEFCB1D37897C5395248A480F2A35A73FD54400E2108DCDBAA5`。

新版从“资料更新”手动更新、导入 ZIP 或回滚；自动检查可选每天／三天／每周／关闭，
仅软件运行时执行。新资料在下一次截图分析生效，已经打开的伤害对照保留原版本。
未配置公开渠道时使用内置离线资料及本地资料包。预存队伍与 OBS 设置分别保存在个人目录，
升级／卸载默认保留；网页版验证成功后的 OBS 密码使用 Windows 当前用户凭据加密保存。

## Windows 安装包（普通用户）

安装包只提供一个用户入口：**Pokemon Champion Assistant**。它在原生窗口中承载 Champion Lab 工作台，队伍仓库、伤害计算、资料百科与设置可在同一窗口切换。队伍仓库支持手动编辑，以及从本地截图或 OBS 导入待核对的队伍配置。伤害页支持形态切换、常用配置、条件场况、乱数击杀概率和展开招式详情。

`ChampionWorker.exe` 是内部更新与自检组件，不是启动入口。当前安装包未签名；已完成开发机上的冻结自检和静默安装验证，尚未在无开发环境的全新 Windows 11 虚拟机上完成验收。队伍和 OBS 设置保存在当前用户目录，升级或卸载默认保留；验证成功后的 OBS 密码由 Windows 当前用户凭据加密保存。

## 从源码运行（开发者）

### 首次安装（Windows）

安装官方 CPython 3.13 和 Node.js 22 或更高版本，并确保 `py -3.13 --version`、`node --version` 可用。克隆仓库后，在项目目录打开 PowerShell：

```powershell
git clone https://github.com/himmely10/pokemon-champion-assistant.git
cd pokemon-champion-assistant
py -3.13 -m venv .venv-ui
.\.venv-ui\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv-ui\Scripts\python.exe -X utf8 launch_assistant.py
```

以后可以双击 `run_assistant.bat` 启动。仓库包含图标、资料快照和已编译的伤害引擎；虚拟环境需要自行创建，无需为了启动程序执行 npm 构建。

### 本地网页开发模式

正式网页源代码位于 `web/`。它不是一份独立的模拟器：队伍、资料、截图识别、OBS 和伤害结果均通过 `127.0.0.1` 上的本地 Python API 调用现有业务模块，服务不会监听局域网地址。OBS 密码不会写入普通设置 JSON 或返回给网页，而是用 Windows DPAPI 加密后单独保存在当前用户目录。

首次构建网页：

```powershell
cd web
pnpm install
pnpm build
cd ..
```

之后双击 `run_web.bat`，浏览器会自动打开 [http://127.0.0.1:32145](http://127.0.0.1:32145)。也可以手动运行：

```powershell
.\.venv-ui\Scripts\python.exe -X utf8 launch_assistant.py --web
```

前端开发时先用 `--web --no-browser` 启动本地 API，再到 `web/` 运行 `pnpm dev`；Vite 会把 `/api` 代理到 32145 端口。

需要截图导入己方队伍时，再安装本地 OCR：

```powershell
.\.venv-ui\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

开发与完整测试：

```powershell
.\.venv-ui\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ocr.txt
.\.venv-ui\Scripts\python.exe -X utf8 -m pytest tests -q
```

如需原有 `.venv` 命令行入口，可用 `py -3.13 -m venv .venv` 创建环境，再在其中安装 `requirements-data.txt`。不要上传个人 `user_data/`、`config/local_ui.json` 或虚拟环境；它们已由 Git 忽略。

## 功能概览

当前阶段：桌面资料台可从完整的 Champions 选队截图识别右侧对手的六只宝可梦，输出简体中文名称，并展示属性、普通／Mega 种族值对照与招式详情。

**减少队伍录入：** 在“我方队伍配置 → 截图导入”选择同一队伍的能力／状态两张截图，或分别从 OBS 采集这两页，即可生成包含培养点、性格、特性、道具和四招的待核对草稿。详见 [截图导入指南](截图导入队伍指南.md)。

**可视化界面：双击 `run_assistant.bat`。** 支持拖入图片，也可连接 OBS WebSocket 选择 Switch 视频源后按按钮截图识别。招式显示属性、威力、命中率，分伤害／变化两组，支持悬浮说明、点击详情与搜索。使用方法及环境安装见 [桌面界面说明](docs/desktop-ui.md)。

桌面使用独立 `.venv-ui` 环境；原有 `.venv` 和下方命令行入口保留。现已支持 M-6 双打招式采用率排序和 50 级六档速度线比较。点击顶部 **我方队伍配置**，可按命名队伍保存培养点、性格、特性、道具和四招；能力／状态页可由本地截图或 OBS 识别为待核对草稿。操作与匹配规则见 [队伍配置使用指南](队伍配置使用指南.md)。

**双向伤害计算：** 主界面先固定本局预存队伍，再在六个已识别的对手槽位间切换。结果自动比较我方四招和对手常用伤害招式；支持普通／Mega 形态、能力等级、顺风及条件速度特性、电光束充能、多段招式 2～5 次独立范围。招式资料区同时显示我方实配速度和对手速度参考。培养配置以已保存队伍为准，双方资料同时显示弱点、抵抗和免疫。需要 Node.js 22+。操作、假设和支持边界见 [双向伤害计算使用指南](双向伤害计算使用指南.md)。

OBS 连接步骤与排错见根目录 [OBS 使用指南](OBS使用指南.md)。v0.2 软件内更新通过公开资料包渠道执行，间隔由更新中心设置，无需 Codex 或账号登录。维护者仍可双击 `update_usage_data.bat` 采集数据，再构建资料包。详见 [采用率与速度线](docs/usage-speed.md) 与 [自动更新说明](docs/data-updates.md)。

现已加入自动资料更新：双击 `update_pokemon_data.bat` 同步，或用下方命令先检查变化。脚本更新物种、属性、种族值、Mega 关联、招式定义和可取得的普通／闪光图标，识别器启动时自动加载当前有效版本。完整用法见 [自动更新说明](docs/data-updates.md)。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py check
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py sync
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py validate
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py rollback
```

2026-09-10 实际同步后共 231 种、398 个形态、782 张图标；391 个形态图标就绪，7 个形态暂仅有资料。原有六只对手识别验证仍通过。更新不会静默删除旧形态或改写已有主名称；种族值与属性有来源，采用率独立更新；双向伤害计算另使用固定规则快照。

## 直接运行

先按上方说明创建 `.venv` 命令行环境，再在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 recognize_opponent.py "图片/例子.png"
```

也可以双击 `run_recognition.bat` 识别 `图片/例子.png`，或将其他截图拖到该批处理文件上。它会打印名称并保留窗口；识别结果页位于 `artifacts/opponent/report.html`，可以用浏览器打开。

换一张截图或指定输出位置：

```powershell
.\.venv\Scripts\python.exe -X utf8 recognize_opponent.py "截图.png" --output-dir "artifacts/new-match"
```

输出包括：

- `names.txt`：右侧从上到下的六个名称，无法确定的位置显示“待确认”。
- `result.json`：名称、候选、相似度、候选差距、原图裁剪坐标和形态歧义。
- `report.html`：可离线打开的完整预览页，包含原图位置框、裁剪图、最佳候选模板和前三个候选。
- `annotated.jpg` 和 `slot_1.png` ～ `slot_6.png`：检查裁剪是否正确。

命令退出码：`0` 六个位置都识别成功；`2` 有待确认位置；`1` 输入、布局或文件错误。

## 本次截图的验证结果

`例子.png` 为 3840×2160。程序识别结果从上到下为：

1. 苍炎刃鬼
2. 风妖精
3. 巨金怪
4. 来悲粗茶
5. 烈咬陆鲨
6. 姆克鹰

六个结果均与人工查看截图一致。当前电脑匹配六个位置约 4.4 秒，首次加载图标库另需少量时间。

按用户确认的展示规则，来悲粗茶的凡作/杰作统一输出“来悲粗茶”，彩粉蝶的不同花纹统一输出“彩粉蝶”，不显示这些外观差异的待确认提示。所有外观图标仍参与匹配，同一合并身份只占一个候选。普通与闪光模板共同参与名称识别，本阶段没有输出闪光判定。

外观合并规则在 `config/recognition_identity_groups.json`，目前登记来悲粗茶和彩粉蝶。后续确认种族值、技能池等对战数据相同的外观形态可加入此表；不能仅凭种族值相同就自动合并。超级进化、地区形态等继续独立识别。原始图标和种族值文件保留原有形态信息。

## 识别方式与结构

流程：**读取截图 → 统一画面尺寸 → 裁剪右侧六个位置 → 遍历本地图标并匹配 → 合并普通/闪光及已登记外观候选 → 检查分数和候选差距 → 输出名称及预览**。

使用 OpenCV 的多尺度模板匹配：将 PNG 的透明背景合成为槽位估计背景，再计算颜色图像的归一化相关性。算法参考 [OpenCV 模板匹配文档](https://docs.opencv.org/4.x/de/da9/tutorial_template_matching.html)。名称来自已有数据索引，识别器没有写入这张截图的六只宝可梦答案。

| 文件 | 职责 |
|---|---|
| `champion_assistant/recognition.py` | 加载图标、裁剪、匹配、拒识、保留相同图标的形态歧义 |
| `champion_assistant/report.py` | 保存 JSON、名称文本、裁剪图片、HTML 预览 |
| `recognize_opponent.py` | 命令行入口，接收截图、布局和输出目录 |
| `config/opponent_team_preview.json` | 六个裁剪区域、模板尺寸和拒识阈值 |
| `config/recognition_identity_groups.json` | 无需区分的外观形态及统一显示名称 |
| `pokemon/current.json`、`champion_assistant/data/storage.py` | 当前有效资料包及固定版本读取；旧平铺目录可兼容 |
| `scripts/update_pokemon_data.py` | 检查、增量同步、完整校验及回滚 |
| `champion_assistant/data/sources.py`、`catalog.py`、`sync.py` | 公开来源解析、身份映射、差异及发布流程 |
| `pokemon/index.json` | 派生兼容索引，目录路径指向有效版本；单次读取应固定资料包 |
| `tests/test_recognition.py` | 真实截图回归、压缩/缩放、换序、空白/噪声等检查 |

布局以 1600×900 为参考坐标，支持相同比例、相同布局的 720p、1080p、4K 等完整截图。`slots` 每项为 `[左, 上, 右, 下]`。若 OBS 加入边框、移动游戏区域或使用另一种菜单布局，需要调整裁剪配置，并通过 `--layout` 指定。

当前阈值为相似度至少 `0.78`，与第二个不同身份候选的差距至少 `0.10`。相似度是匹配分数，**不是正确率或概率**。低分、空白和候选接近的区域不会强行输出名称。

## 测试与适用范围

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recognition.py -q
```

本次 13 项检查通过：原始截图、1280×720 JPEG 压缩版、六个位置换序、三种空白背景、随机噪声、错误画面比例、超级进化/地区形态和两种彩粉蝶花纹的合成图标，以及近似外观模板合并后不影响候选差距的检查。

目前真实样本只有用户提供的这一张截图；压缩、缩放和换序仍然来自同一个样本，合成图标也不代表真实游戏画面表现。因此当前结果验证了这一路线的可行性，尚不能推断其他队伍、遮挡、动画和不同采集设备上的总体准确率。默认布局要求选队画面完整且右侧图标可见。

## 在新电脑准备环境

本次在 Windows、Python 3.13.5 上运行验证。项目运行依赖记录在 `requirements.txt`：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

自动更新额外安装 `requirements-data.txt`；运行全套测试安装 `requirements-dev.txt`，执行 `python -m pytest tests -q`。旧历史导出脚本另需 `json5`，现已由新更新入口替代，详见 `docs/data-updates.md`。

桌面版已经让对手选队识别与我方能力／状态页导入共用 OBS 截图入口；每次按按钮读取一帧，不持续分析视频。
