# tools 脚本清单

开发/验证/发布脚本。分类速查：

| 目录 | 用途 | 数量 |
|---|---|---|
| `publish/` | 本地打包发布 | 1 |
| `tests/` | 自动回归测试（自动清理/还原，可无人值守跑） | 11 |
| `manual/` | 人工交互验证（脚本准备环境+采样，**人操作**） | 2 |
| `visual/` | 视觉/主题/字形/截图验证（出 PNG，判定人工看） | 12 |
| `utils/` | 单项工具：查询/控制/截图/配置 | 18 |
| `archive/` | 一次性历史脚本（留档，不再维护） | 6 |
| `lib/` | （规划中）Python 公共库 | — |

**警告**：清理/回归脚本会无差别关闭所有 WindowMerger/Notepad/mspaint——**包括你自己开着的实例**（Notepad 是强杀，未保存内容丢失）。跑之前确认没有正在使用的窗口。

**测试窗约定**：一律 mspaint，不起 notepad（用户要求，窗口人工选择）；Win11 记事本单实例多标签，同名目标会去重只吸一个，属预期。

**脚本约定**：PowerShell 5.1（Windows 自带）。内容一律 **ASCII-only**（PS 5.1 把 UTF-8 无 BOM 当 ANSI 读，中文会破坏解析），诊断输出用英文。

## publish/

| 脚本 | 用途 |
|---|---|
| `Publish.ps1` | 本地打包发布：WM_CLOSE 优雅关运行实例 → dotnet publish（复用 FolderProfile.pubxml）→ `publish\WindowMerger-<版本>-win-x64.exe`。`-Version 1.2.3` 覆盖版本 |

## tests/（自动回归）

| 脚本 | 回归点 |
|---|---|
| `RunTestFlow.ps1` | 全流程：清理 → 开测试窗 → CLI 吸附 → 命中/矩形断言 → 还原置顶 |
| `CrossDpiSeamTest.ps1` | 跨 DPI 缝隙：96DPI mspaint 吸进 150% 宿主，子窗口可见缘与格子四边 ≤1px；左屏不在/非 100% 自动 SKIP |
| `ShortcutCreateTest.ps1` | 快捷方式生成：mspaint 单侧 + UIA 点按钮，校验 .lnk 参数含 `--left/--left-exe` 完整路径；mspaint 被占 SKIP 不强杀 |
| `LaunchAttachTest.ps1` | 拉起吸附：目标未运行，宿主带 `--left 名字 --left-exe 完整路径` 启动，断言宿主自己拉起并吸附成功 |
| `OrphanE2ETest.ps1` | 孤儿清理端到端：强杀宿主留孤儿 → 重启宿主启动清理摘除 TOOLWINDOW |
| `PidModeTest.ps1` | CLI PID 模式：PID/名字混合吸附 + 无窗口 PID 的报因路径 |
| `ReleaseTest.ps1` | 释放路径：全部释放后子窗口摘 TOOLWINDOW 且窗口完好 |
| `ExcludeSelfTest.ps1` | 排除自身：另一个 WindowMerger 实例的宿主不可被 CLI 吸附 |
| `CursorDropTest.ps1` | 光标落点判定：光标在格外/窗口中心在格内 → 不吸附（旧中心逻辑回归） |
| `GhostCycleTest.ps1` | 吸附/释放循环的幽灵任务栏按钮检查（UIA + 窗口枚举） |
| `AltTabZRepro.ps1` | Alt+Tab 切回宿主后子窗口 z 序自愈回归（z 链探针） |

## manual/（人工交互验证）

| 脚本 | 用法 |
|---|---|
| `ManualDragTest.ps1` | 最大化拖顶条还原：准备环境 + 每 150ms 采样时间线，**人工拖动**后按 ENTER 打判定 |
| `CoveredDragTest.ps1` | 遮挡格拒收：置顶遮罩盖右格，**人工两步拖拽**（拖遮挡格=拒收，拖空格=吸附） |

## visual/（视觉验证，截图判定人工看）

| 脚本 | 验证点 |
|---|---|
| `ThemeMenuTest.ps1` | UIA 开主题菜单、逐项选择，校验配置值与 ✓ 标记（纯 UIA，锁屏可用） |
| `ThemeToggleVisualTest.ps1` | UIA 切深/浅色各截一张对比 |
| `ThemeMenuShot.ps1` | 真实点击截展开的主题菜单 |
| `TooltipShot.ps1` | 悬停主题按钮截 Tooltip 弹层 + 像素采样（Tooltip 是独立弹窗，必须全屏截） |
| `HoverVisualTest.ps1` | 悬停分隔条/关闭/最大化/释放逐个截图（强制深色） |
| `DividerHoverTest.ps1` | 分隔条悬停高亮竖条截图 |
| `HintPaneShot.ps1` | 空格占位提示：空格填充+文案，吸附后该侧消失恢复透明 |
| `GlyphVerify.ps1` | 内嵌 FA 字形渲染验证（PrintWindow，z 序免疫） |
| `IconVerify.ps1` | exe 内嵌图标 + 运行中任务栏图标验证 |
| `PickBtnDump.ps1` | 选窗按钮字形码点 dump + 4x 放大截图 |
| `SideBtnShot.ps1` | 顶条右侧按钮区截图 |
| `TopBarLeftShot.ps1` | 顶条左侧图标+标题截图 |

## utils/（单项工具）

| 脚本 | 用途 |
|---|---|
| `Atomic.ps1` | 置顶+截图+自动还原置顶（排查遮挡；截图后必须还原层级） |
| `Shot.ps1` | 全屏/区域截图存 PNG |
| `ZoomPng.ps1` | PNG 区域放大（检字形/像素） |
| `Rect.ps1` | 按 hwnd/标题查窗口矩形 |
| `Hit.ps1` | 查某点 WindowFromPoint 命中（窗口标题/类/PID） |
| `WinCmd.ps1` | 按 hwnd 执行 minimize/restore/close |
| `Drag.ps1` | 注入式拖动（受前台锁干扰，不可靠，回归别走这条） |
| `ZDump.ps1` | 只读 z 序 dump（宿主/子窗口相邻关系） |
| `StateProbe.ps1` | 全状态探针：宿主/子窗口/命中/前台 |
| `DividerProbe.ps1` | 分隔条处命中探针（验证宿主盖住子窗口隐形边） |
| `AttachCheck.ps1` | 吸附状态确定性校验（TOOLWINDOW + 矩形，无屏幕探针） |
| `InstanceTimes.ps1` | 列出运行中宿主实例启动时间 |
| `CloseHostOnly.ps1` | 只优雅关 WindowMerger（WM_CLOSE，不动其他应用） |
| `CloseInstance.ps1` | 优雅关宿主 + 强杀测试窗（重建 exe 前清理） |
| `SetTheme.ps1` | 改 config.json 主题（Auto/Dark/Light） |
| `RestoreTheme.ps1` | 主题恢复 Auto |
| `ResetRatio.ps1` | 分隔比例复位 0.5 |
| `OrphanRescue.ps1` | 孤儿扫描/救援：扫描全部 TOOLWINDOW 孤儿，`-Rescue -ProcName xxx` 摘样式+拉回屏 |

## archive/（一次性历史脚本，留档不维护）

| 脚本 | 备注 |
|---|---|
| `AltTabRepro.ps1` | 真实 Alt+Tab 输入复现（z 序 bug 排查期产物，被 `tests/AltTabZRepro.ps1` 取代） |
| `NotepadPidDiag.ps1` | Win11 记事本单实例 PID 诊断（stub 交接排查期产物） |
| `BaselineShot.ps1` / `EdgeCompare.ps1` | 隐形边调查期基线截图/边缘扫描对照 |
| `VisualCheck2.ps1` | PrintWindow 宿主截图（被 `utils/` 截图系列覆盖） |
| `GenIco.ps1` | 生成多尺寸 .ico（图标已入库 `assets/`；改图标时再用，注意默认输出路径是旧仓库位置需改参） |
