# 第三方组件与资料

本项目是社区辅助工具，与任天堂、The Pokémon Company 或 Game Freak 无隶属关系。
宝可梦名称、图标与游戏相关素材的权利属于其各自权利人。参考资料来源为
52Poké、OP.GG 和 PokéChamp DB；来源、抓取时间和校验摘要随公共资料包保留。

安装版包含 Python（PSF 许可）、Node.js（MIT 及随附第三方许可）、
PySide6 / Qt（LGPLv3，动态库）、OpenCV（Apache-2.0）、NumPy（BSD）、
Pillow（HPND）、Requests（Apache-2.0）、RapidOCR（Apache-2.0）、
ONNX Runtime（MIT）、PaddleOCR 模型（Apache-2.0）等组件。
软件未限制使用者替换符合接口的 Qt 动态库；项目使用原版 PySide6 wheel。
具体依赖元数据、许可证副本在安装目录 `_internal/licenses`。

伤害引擎来自 Smogon damage calculator；其 LICENSE、来源修订和本地适配说明
位于 `_internal/damage_engine/vendor/smogon-calc`。该目录保留源代码和编译产物。

安装包生成时会复制可用的依赖许可证，并记录 Python、Node、模型及资源 SHA-256。
发布者应在正式分发前复核资料素材的使用条件与第三方许可要求。

应用图标为本项目原创 SVG：深色底板、青色速度折线与金色指示点。
