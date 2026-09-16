# 资料包与程序发行

## 资料发行当前能力

维护者可在本地或 GitHub Actions 构建资料 ZIP。构建完成前会调用软件自己的 `UpdateService.install()` 导入临时目录，再逐项比较图鉴、招式和采用率。只有成功产物才会写入输出目录。当前没有配置真实公开下载地址；本地包可导入，CI 产物不能据此声称公众已可自动更新。

```powershell
.\.venv-ui\Scripts\python.exe -X utf8 scripts/build_data_bundle.py --data-dir pokemon --output-dir artifacts/data-dist
```

若已选定公开 HTTPS 包目录，可额外传入：

```powershell
.\.venv-ui\Scripts\python.exe -X utf8 scripts/build_data_bundle.py --data-dir pokemon --output-dir artifacts/data-dist --base-url https://example.org/pokemon-data/
```

示例域名是占位符。这个参数只生成本地 `channel.json` 候选，不会上传文件，也不会修改远程渠道。未传参数时仅产出离线 ZIP 与报告；不要将离线报告作为在线渠道清单。

输出包括：

- `references-<内容摘要>.zip`：可在软件更新中心导入的资料包。
- `latest-build.json`：资料与赛季、来源时间、陈旧统计项、客户端往返结果、大小和 SHA-256。
- `build-state.json`：上次成功构建的语义摘要，供下次跳过无变化数据；应与其 ZIP 一起保留。
- `channel.json`：仅指定 HTTPS 目录时产生的候选渠道清单。

相同来源快照在相同 Python／SQLite／压缩库环境中产生相同 ZIP 字节。采集时间变化但内容不变时，已有输出目录会复用旧 ZIP；最新采集时间另记在 `latest-build.json`，不会给旧包重标日期。删除构建状态或缓存后不能承诺跨观察批次去重，但相同精确输入仍可复现。

包内只允许公共 JSON、PNG、SQLite。普通与 Mega 身份、缺失值、来源日期均保留。原始网页继续留在维护者源目录；传输包不包含 HTML、执行脚本、队伍库、OBS 密码或用户截图。SHA-256 用于检查内容完整性，不能代替独立签名或可信的 HTTPS 来源。

## 维护者 CI

`.github/workflows/data-bundle.yml` 提供手动运行与每天一次的采集构建。日程为 UTC 01:23（北京时间 09:23）；GitHub 调度可能延迟，默认分支上的工作流才会按日程运行。详见 [GitHub 工作流事件文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。这与用户软件运行期间的更新检查、Codex 自动化互相独立。

手动运行可关闭 `refresh`，直接验证仓库／缓存的现有资料。`base_url` 输入或仓库变量 `DATA_PACKAGE_BASE_URL` 可生成渠道候选；不应填入凭据。工作流只具有仓库读取权限，没有发布 Release、修改稳定渠道或推送代码的步骤。

CI 顺序：恢复上次有效构建缓存 → 隔离的维护者资料目录 → 包契约测试 → 静态资料采集 → 使用率采集 → 构建与实际客户端导入验证 → 上传候选产物 → 保留成功缓存。

少量使用率失败沿用原采集器的同赛季旧值，并在 `stale_entries` 标明；超过失败阈值、图鉴大量消失或结构异常时停止，不生成新的稳定清单。缓存可能被 GitHub 回收，需把正式发布产物存放在选定渠道，而非仅依赖 Actions 缓存。缓存机制与产物保留细节见 [actions/cache](https://github.com/actions/cache)、[actions/upload-artifact](https://github.com/actions/upload-artifact)。

## 发布到真实渠道的顺序

1. 从成功构建下载 ZIP、报告及候选清单，确认赛季、版本、陈旧项和目标地址。
2. 先把 ZIP 上传到以内容摘要命名的最终 URL，不覆盖其他版本。
3. 从该 URL 重新下载，确认大小和 SHA-256 与报告一致。
4. 最后原子更新稳定 `channel.json`。客户端读到缓存旧清单仍对应完整旧包；上传中断时稳定清单保持不变。
5. 保留上一有效包与清单用于回退；用户队伍不随公共资料回滚。

实际公开地址、上传权限尚未配置，因此上述远程发布步骤目前需由维护者在选定托管后执行。不要将私有源码仓库的 token 写入客户端或渠道 URL。

## 程序安装发行门禁

程序发行与资料 ZIP 分开：安装包包含 Python、Qt、Node 等必要运行依赖；资料包不能更新可执行代码。Setup.exe 的最终构建、签名和干净 Windows 安装／升级验证由 U10 完成。

正式宣布可发布前，需要在无开发环境的 Windows 11 x64 检查：首次启动、图片识别、队伍保存、双向伤害、OBS 引导、离线资料导入，以及升级后队伍／设置仍在。开发机或临时目录中的导入成功不能替代这项验证。安装和暂存路径还需覆盖长路径；本地构建器用较短的系统暂存路径避免不必要的目录嵌套。

## Windows 候选构建入口

手动运行 `.github/workflows/windows-release.yml` 可启动候选流程。它使用 Python 3.13、Node 22.20.0、pnpm 12.4.1 和 `requirements-build.txt` 中的 OCR／打包依赖，先安装并构建 `web/` 生产资源，再下载并校验三个离线模型、构建资料组合和冻结程序。它实际运行 `ChampionWorker.exe --self-check`，通过后使用 Inno Setup 生成 Setup.exe，并仅上传候选 artifact。

本地对应入口如下；其中安装资料组合可在 Python 中调用 `UpdateService.install()`，或通过已有软件更新入口完成：

```powershell
.\.venv-ui\Scripts\python.exe -X utf8 scripts/build_windows.py --data-dir artifacts/release-data
.\artifacts\dist\PokemonChampionAssistant\ChampionWorker.exe --self-check --output artifacts/release/frozen-self-check.json
.\artifacts\dist\PokemonChampionAssistant\ChampionLabWeb.exe
```

`--self-check` 支持 `--image`、成对的 `--ability`／`--status` 参数；对个人队伍库执行诊断时，还需 `--exercise-user-store` 并设置隔离的 `CHAMPION_USER_DIR`。这些诊断不应指向真实用户目录。`ChampionLabWeb.exe` 会自动打开浏览器，关闭其命令窗口即停止本地服务。Setup.exe 使用 `packaging/installer.iss` 编译；安装向导当前为英文，应用界面为简体中文。

证据产物包括 `release-candidate.json`（安装器摘要与状态）、`build-manifest.json`（资源摘要）、`model-sources.json`（官方模型来源与哈希）、`frozen-self-check.json`（实际冻结运行结果）。当前仍标记候选：**干净 Windows 11 VM 未验证，在线稳定渠道未部署，发行签名未配置**。验证范围和待完成门禁见 [Windows 打包验证记录](validation/packaging.md)。
