# 自动更新宝可梦资料

入口为 `scripts/update_pokemon_data.py`。可以双击根目录 `update_pokemon_data.bat` 完成一次同步；识别操作本身不联网。命令可以从任意目录启动，默认资料根目录根据脚本位置定位。

## 使用

在项目根目录执行：

```powershell
# 新环境安装采集依赖（已有环境不必重复安装）
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt

# 联网检查变化，保存差异报告，不替换有效数据
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py check

# 下载变更、校验并发布；重复运行可复用已下载图片
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py sync

# 离线检查当前资料包的清单、图片、属性和种族值
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py validate

# 恢复上次发布的资料包
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py rollback
```

`check` 退出码：0 表示无更新，2 表示发现更新，1 表示错误；`sync / validate / rollback` 成功为 0，失败为 1，用户取消为 130。完整差异及错误报告位于 `pokemon/_reports/`，`latest.json` 是最近一次操作结果。检查仍会写网页缓存和报告。

其他选项：

```powershell
# 强制重新验证图片 URL，检查同一 URL 的图像是否有更新
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py sync --refresh-images

# 校验具体包；回滚到指定包（将占位符替换为 current.json/history 中的 ID）
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py validate --bundle "pokemon/_versions/<包ID>"
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py rollback --to "<包ID>"

# 从已保存页面检查差异；明确标记 offline_snapshot，不代表检查了最新版本
.\.venv\Scripts\python.exe -X utf8 scripts/update_pokemon_data.py check --source-dir docs/research/2026-09-10-opgg
```

`--data-dir` 可以指定另一个已有目录。离线页面模式不会查询百科文件库；`sync --source-dir` 若页面引用了本地没有的图标，仍需联网下载图片。当前支持从既有项目资料初始化，空目录不会凭空建立旧站映射。

## 本次同步内容与来源

2026-09-11 起，同步同时保存 OP.GG 的招式定义到资料包 `moves.json`，包含属性、分类、威力、命中率、PP、先制度、目标与说明。招式独立变化会触发新版本，来源招式清单意外丢失时保留旧包。首轮导入 920 条定义；界面再按该宝可梦的招式池、禁用列表和来源可用性筛选。它们不是双打使用率统计。旧包中的已校验 OP.GG 原始页面仍可供界面离线解析。

同步后重启桌面界面使用新版；已打开的资料台及其识别器继续使用原来的同一版本。

- 从 [OP.GG 完整图鉴](https://op.gg/zh-cn/pokemon-champions/pokedex)的公开内嵌数据读取身份、简体别名、六项种族值、属性及 Mega 关系，保存原始页面。不是只抓排行榜或首屏十条。
- 从 [52Poké Champions 名单](https://wiki.52poke.com/zh-hans/宝可梦列表（Champions）)取得普通／闪光图标。主列表落后时，使用公开 [MediaWiki 文件元数据查询](https://www.mediawiki.org/wiki/API:Imageinfo)，核验已知命名规则对应的文件是否已上传，再下载返回的真实 URL。未知形态代码不猜测。
- 本包面向双打项目，但静态种族值不区分单／双打。**没有导入对战使用率、培养配置或伤害公式**，不把来源规则标签 M-A/M-B/M-C 当作赛季或当前合法性证明。取消原采集器固定 M-5 的限制，当前静态包 `reference_season` 为 null。
- 保留既有主名称和 `source_slug`，通过 `config/source_aliases.json` 映射来源别名与特殊形态。相同种族值不代表可以合并战斗形态；来悲粗茶、彩粉蝶的识别输出规则继续使用独立外观合并表。

当前实测记录见 `docs/validation/data-updates.md`。原 `collect_pokemon.py / export_pokemon.py` 仅保留用于复现历史采集；启用版本目录后会阻止其覆盖有效索引。

## 文件结构与读取约定

```text
pokemon/
  current.json                  # 权威入口：有效版本 ID、manifest 哈希、历史版本
  index.json                    # 派生兼容索引，directory 指向版本内真实目录
  _versions/<包ID>/
    manifest.json               # 每个已发布文件的 SHA-256
    index.json                  # 当前包独立可读的全量索引
    source_catalog.json         # 本次来源清单，不混入历史网页缓存
    source_aliases.json
    recognition_identity_groups.json
    _sources/                   # 本次公开响应存档
    宝可梦名字/
      宝可梦名字.json
      宝可梦名字.png            # 无图条目暂缺，不伪造素材
      宝可梦名字_闪光.png
  _update_cache/                # 按 URL 缓存元数据、按内容哈希缓存响应
  _reports/                     # 每次操作报告
  _staging/                     # 尚未发布的暂存；失败残留不参与读取
  妙蛙花/ ...                   # 原平铺文件保留为历史原件，不再表示最新数据
```

新代码通过 `resolve_dataset(data_dir)` 获取当前不可变版本，一次识别只解析一次；既有识别器保持原图标缓存，新建识别器才加载新包。根目录兼容索引可供简单脚本查看，但连续读取应固定一个版本目录；若发布时进程在兼容导出前中断，再次 `sync` 可修复该派生文件。

新增字段包括 `record_id`、`opgg_key`、`types/type_names`、`mega_form_ids`、`source_presence`、`recognition_ready` 和 `types_ready`。`mega_form_ids` 关联其他完整记录，可读取其属性及种族值；它不表示当前宝可梦已超进化。历史条目的旧来源原始页面仍保存在原平铺 `_sources/`；本版有 OP.GG 对应条目的来源存档在版本包内。

`recognition_ready=true` 要求普通／闪光图标均已通过规格和哈希检查；只有资料的条目仍可查询，识别器会跳过。不同站点未收录的历史外观不会自动删除；例如 OP.GG 未逐项给出飘浮泡泡其他天气形态时，不把普通形态属性覆盖到它们。

## 失败处理

网页每次重新请求或使用 HTTP 条件重验证；图片默认复用已校验内容，使用 `--refresh-images` 可检查图片本身的更新。网络超时、429、错误页面、截断清单、下载中断或文件校验失败均停止发布。没有兼容图片与图片下载失败不同：前者可收录资料并标待就绪，后者不能宣称整个同步批次成功。

与上次同源清单相比减少超过 10% 时阻止发布，需检查页面结构／完整性和实际名单变动；不提供绕过校验的强制覆盖开关。减少较少的条目也只记录退签候选并保留历史，不静默删除用户数据。

所有更新写入暂存区，整个包完成后才原子切换 `current.json`；首次升级会先保存原目录的可回滚包。发布与回滚受进程锁保护，程序退出后锁由操作系统释放。校验清单拒绝绝对路径、目录穿越和链接逃逸；抓取的页面只解析为数据，不执行脚本。
