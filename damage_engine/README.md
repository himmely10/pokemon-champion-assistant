# 本地 Champions 伤害引擎

Python 通过 `bridge.cjs` 的 JSON stdin/stdout 调用 Node.js；无网络调用、用户字符串执行或第三方账号。运行环境 Node.js 22+，本机验证 22.20.0。`vendor/smogon-calc/dist` 随项目分发，运行时不依赖 node_modules。

## 来源和固定版本

- 上游：[smogon/damage-calc](https://github.com/smogon/damage-calc/tree/e7fd7e59f3eef7ea42fba3c8b83261cb4a14109d/calc)
- 提交：`e7fd7e59f3eef7ea42fba3c8b83261cb4a14109d`
- MIT 授权，完整许可见 `vendor/smogon-calc/LICENSE`，来源记录见 `PROVENANCE.json`。
- 采用源码中的 Champions generation 0。npm 的 0.11.0 发行包没有本次使用的 Champions 规则，不能直接替换。
- 桥接使用官方 `adaptable` 入口与显式 `Generations.get(0)`，绕开浏览器兼容入口对导出变量的重绑定。

## 本地补丁

`state.ts`、`field.ts` 增加并克隆 `isSingleTarget`；`mechanics/champions.ts` 的两个群攻判断读取此字段。它只关闭群攻减伤，保留 `gameType: Doubles` 以维持双打的墙修正。不要将场地改成 Singles 来模拟只有一个有效目标。

桥接针对扫墓根据显式倒下同伴数覆盖威力，并拦截缺输入／未核验特殊招式、多段招式、未知道具／特性／性格以及不一致的属性／种族值。变化招式由本地资料明确路由为无直接伤害。

## 重新构建

在本目录执行：

```powershell
npm.cmd ci
npm.cmd run build
```

构建依赖固定于 `package-lock.json`。`catalog.json` 是该提交的 generation 0 身份／招式等元数据快照；更新规则时必须同步生成，检查本地身份映射、保留补丁，运行数值及界面回归，再修改 Python 中的 `RULE_VERSION`。不可只更新元数据或以每日数据更新代替规则审核。

从项目根目录验证：

```powershell
.\.venv-ui\Scripts\python.exe -X utf8 -m pytest tests/test_damage.py tests/test_damage_ui.py -q
```

产品使用方法见根目录 `双向伤害计算使用指南.md`，机制支持与独立预期见 `docs/research/damage-rules.md`。
