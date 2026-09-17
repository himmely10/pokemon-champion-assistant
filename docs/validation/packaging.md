# Windows 打包与发行验证记录

状态：**候选构建验证中；干净 Windows 11 x64 虚拟机尚未验证；在线稳定渠道尚未部署。** 本文区分已观察的证据、脚本可执行步骤和仍未完成的发布门禁。

## 已有本地证据

| 范围 | 证据 | 结论与边界 |
|---|---|---|
| 源码自检 | `artifacts/work/source-smoke.json`，`frozen=false`、`status=ok` | 资料、Node、临时队伍库、伤害桥接、识别通过；仅开发环境 |
| 既有冻结程序自检 | `artifacts/work/frozen-smoke.json`，`frozen=true`、`status=ok` | 内置运行时与识别可执行；不等于最终 v0.2 安装包验收 |
| 既有冻结 OCR 自检 | `artifacts/work/frozen-ocr-smoke.json`，`frozen=true`、`status=ok` | OCR 在冻结程序中可运行；不证明所有截图均准确 |
| 完整 SQL 资料包导入 | `artifacts/u7-data-dist/latest-build.json` | 398 形态、231 物种、920 招式、782 图标及 259 采用率条目经真实客户端导入等价通过 |
| 资源清单单元测试 | `tests/test_release_manifest.py`，7 项通过 | 正常、损坏、缺文件、漏列必需模型、未知 schema、越界路径与只读验证 |
| 新 Windows CI | `.github/workflows/windows-release.yml` | 工作流已编写，尚未在远程 runner 实跑；不能宣称 CI 构建通过 |
| 干净系统安装／升级 | 无独立 VM 证据 | **待验证** |
| 稳定渠道／签名 | 未配置 | **未部署／未签名** |

上述旧冻结程序报告是打包可行性的证据，不覆盖之后的所有代码修改。最终候选必须重新生成对应版本的 `build-manifest.json`、`frozen-self-check.json` 和安装器 SHA-256，不能把旧报告复制为新版本通过证明。

## 离线 OCR 模型来源

版本锁定 `rapidocr==3.9.2`、`onnxruntime==1.30.0`。构建时使用 RapidOCR 已安装包中的 `default_models.yaml` 核对 RapidAI 官方发布地址，再检查以下固定 SHA-256。三份本地已有模型的哈希与该元数据一致。

| 文件 | SHA-256 | 固定来源 |
|---|---|---|
| `PP-OCRv6_det_small.onnx` | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` | [RapidAI v3.9.2 检测模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx) |
| `PP-OCRv6_rec_small.onnx` | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` | [RapidAI v3.9.2 识别模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/rec/PP-OCRv6_rec_small.onnx) |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` | [RapidAI v3.9.2 方向模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx) |

CI 将来源、哈希和文件大小写入 `artifacts/release/model-sources.json`。下载失败、元数据改变或哈希不符会停止构建。最终程序自带模型，普通用户无需再次下载；模型哈希验证与图像识别准确率验证是不同的检查。

## CI 候选构建顺序

1. Windows Server 2025 runner，Python 3.13，Node **22.20.0**；Node 版本与随包 `licenses/Node-LICENSE.txt` 匹配。安装 `requirements-build.txt` 及测试依赖。
2. 从上述官方地址取得并验证模型；执行仅资源清单相关的单元测试。
3. 运行 `scripts/build_data_bundle.py`，再用 `UpdateService.install()` 导入 `artifacts/release-data`，得到静态／采用率的固定组合。
4. 运行 `scripts/build_windows.py --data-dir artifacts/release-data`；随后校验冻结产物 `_internal/build-manifest.json` 的必需项及逐文件摘要。
5. 实际运行冻结 `ChampionWorker.exe --self-check`。清除开发环境 `PYTHONPATH`，将 PATH 限制为 Windows 系统目录；用 `CHAMPION_USER_DIR` 指向隔离的测试目录，从程序目录外执行资料、内置 Node、队伍存储、伤害、识别和 OCR 自检。
6. 使用 runner 上的 Inno Setup 编译候选 Setup.exe，记录安装器大小和 SHA-256。
7. 上传候选及证据为 Actions artifact。没有自动创建正式 Release 或修改在线稳定渠道的步骤。

runner 自带开发工具，因此第 5 步验证依赖隔离，仍不能代替没有 Python／Node／OBS 的干净 Windows 11 用户环境。Windows Server runner 的预装工具范围见 [GitHub runner 镜像说明](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)。

## 最终人工发布门禁

在新建 Windows 11 x64 VM 上保存系统版本、显示缩放和每一步结果：

- 安装器以普通用户身份完成安装，不要求安装 Python 或 Node；首次启动可找到随包资料与模型。
- 断网完成示例识别、队伍保存和普通／Mega 双向伤害；OCR 字段不确定时进入核对流程。
- 1366×768、150%／200% 显示缩放下可操作保存按钮与详情区；窗口缩放、最大化和返回行为正常。
- 首次无 OBS 时显示指引；安装 OBS 并启用 WebSocket 后连接真实采集卡画面。开发机连接成功不能代替这项新环境验证。
- 保存有四招、培养点、性格、特性及道具的整队，升级安装后逐项一致；公共资料更新和回退不覆盖个人库。
- 卸载后个人资料仍保留，再次安装可恢复；深路径、中文用户名和含空格目录无意外失败。
- 验证断电／中断或损坏资料包保持上一有效分析组合。

只要上述门禁缺少证据，发行记录继续标 `candidate`、`clean_windows_vm=not_verified`。公开地址与签名没有实际配置前，保留 `stable_channel=not_deployed`、`code_signing=not_configured`。

## v0.4.0 队伍截图导入候选验收

本节记录最终 v0.4.0 候选的本机证据；没有实际完成的门禁仍标待验证，不沿用 v0.3.0 安装器摘要。

| 门禁 | 必须保存的 v0.4.0 证据 | 当前状态 |
|---|---|---|
| 源码与前端回归 | `pytest` 356/356、Vitest 16/16、lint、Vite build | 本机通过 |
| 冻结资源与自检 | 冻结 `_internal/build-manifest.json` 版本 0.4.0；`artifacts/release/v04-frozen-self-check.json` 包含识别、OCR 与伤害 | 本机通过 |
| 队伍截图导入 | 安装后 HTTP 接口以本地能力／状态图各识别六槽、合并未保存草稿；前后端测试覆盖纠错／冲突／显式保存；真实 OBS 采集未重测 | 部分通过，OBS 待验证 |
| v0.3.0 覆盖升级 | 从 v0.3.0 隔离样本复制个人队伍库，`PRAGMA integrity_check=ok`，记录和 revision 一致；设置与 DPAPI 凭据样本缺失 | 部分通过，凭据待验证 |
| 安装／卸载与现有功能 | 隔离安装与卸载成功；安装后的自检包含对手识别、普通／Mega 伤害；单窗口人工操作未重测 | 部分通过 |
| 候选安装包 | `PokemonChampionAssistant-0.4.0-windows-x64-Setup.exe`，354,834,381 字节，SHA-256 `0338D6C41B272F86AE88E299BA8ECC35989C1A4D00F0C08D682C3FAC898764F2` | 本地已生成，GitHub 上传状态另记 |
| 独立发布门禁 | 干净 Windows 11 VM、签名、稳定渠道 | 未验证／未配置 |

只有本地可用门禁都通过且无阻断性代码复审发现时，才可上传 v0.4.0 预发布安装包。当前文档没有宣称 v0.4.0 已完成构建、升级或真实 OBS 验收。


## 2026-09-13 本地安装演练进展

- 已按新增战斗与 OBS 队伍导入功能重新编译 `PokemonChampionAssistant-0.2.0-windows-x64-Setup.exe`。最终本地候选大小 197,162,930 字节，SHA-256 为 `5A0892B07679C38FD2B1A648233882D0464EE0A38F740288C951133EAB6F75C8`。
- 最新冻结自检 `artifacts/work/v02-final-frozen-smoke.json` 通过：398 形态、`例子2` 六槽识别（含巨钳螳螂）、`能力2／状态2` 六成员完整 OCR 草稿、实际普通伤害 102–122、Mega 伤害、内置 Node 与个人队伍库。总耗时约 49.93 秒；仍是开发机而非干净 VM。
- OBS 32.2.2的Switch2实际取图成功，3840×2160，约0.36秒；报告 `artifacts/work/v02-obs-check.json` 不包含密码。
- 编译演练安装器0.1.99（使用当前实现，仅模拟旧安装版本号，不是历史v0.1产品），成功安装到 `artifacts/安装 验收`。独立用户目录完成伤害和队伍保存自检：`artifacts/work/upgrade-before.json`。
- 随后完成 0.2.0 覆盖安装和升级后冻结自检；`artifacts/work/upgrade-before.json` 与 `artifacts/work/upgrade-after.json` 的个人队伍指纹均为 `2648dcf16e321073a607a31ffb57a386222d2ced6f9e0bea4d0c6ac03a2775b2`，说明该安装演练中队伍数据保持一致。卸载再装仍待验证。
- 最终源码测试 **289 项全部通过**，包括伤害、速度、主窗口、OBS 队伍截图入口、两组真实 OCR 和打包资源门禁。

## 2026-09-16 v0.3.0 网页安装包候选验证

- 构建器实际运行 Vite 生产构建，并将 `web/dist/index.html`、带哈希的 JavaScript/CSS 与其他静态资源写入冻结资源清单。缺失入口、JS 或 CSS 时构建会失败。
- 冻结目录包含 `PokemonChampionAssistant.exe`、`ChampionWorker.exe` 和新增的 `ChampionLabWeb.exe`。冻结自检通过：398 形态、内置 Node `v22.20.0`、队伍存储、普通伤害 102–122 与 Mega 伤害 116–140均正常。
- 实际将 Setup 静默安装到仓库内隔离目录；开始菜单同时生成桌面程序和 **Champion Lab Web** 入口，且两者均指向安装目录。
- 已安装的 `ChampionLabWeb.exe` 在隔离用户目录下返回 HTTP 200，`/api/bootstrap` 报告 `version=0.3.0`、`api=local`、398 形态；第二次启动复用已有实例并以 0 退出。
- 安装演练后使用安装包自带卸载器清理，隔离安装目录和开始菜单组均已移除，候选 Setup 保留。
- 候选包大小 205,747,926 字节（196.22 MiB），SHA-256 为 `AB3DC0F02AD1F803B8743FE2F32359B805E6BD89B1369D09834396DA3EB14112`。
- 上述均在开发机完成；干净 Windows 11 VM、签名及公开稳定通道门禁仍未完成，因此本产物仍是 candidate。
