# tools 脚本清单

开发/验证/发布脚本，**Python 3.14**（公共库 `lib/wm.py` ctypes Win32 封装 + `lib/wm_uia.py` UIA），调用方式 `py tools\<目录>\<脚本>.py`。全量对照（原名 → 新位置）：

| 目录 | 用途 | 数量 |
|---|---|---|
| `publish/` | 本地打包发布 | 1 |
| `tests/` | 自动回归测试（自动清理/还原，可无人值守跑） | 11 |
| `manual/` | 人工交互验证（脚本准备环境+采样，**人操作**） | 2 |
| `visual/` | 视觉/主题/字形/截图验证（出 PNG，判定人工看） | 12 |
| `utils/` | 单项工具：查询/控制/截图/配置 | 18 |
| `archive/` | 一次性历史脚本（**PowerShell 留档，不再维护**） | 6 |
| `lib/` | 公共库：`wm.py`（ctypes Win32/截图/进程/config）、`wm_uia.py`（comtypes UIA） | 2 |

**依赖**：`py -m pip install pillow comtypes`（截图存 PNG、UI Automation）。应用本身不需要 Python。

**警告**：清理/回归脚本会无差别关闭所有 WindowMerger/Notepad/mspaint——**包括你自己开着的实例**（Notepad 是强杀，未保存内容丢失）。跑之前确认没有正在使用的窗口。

**测试窗约定**：一律 mspaint，不起 notepad（用户要求，窗口人工选择）；Win11 记事本单实例多标签，同名目标会去重只吸一个，属预期。

**脚本约定**：UTF-8 中文注释可用（lib 导入时重配 stdout UTF-8）；诊断输出标记保持英文（`NO_HOST` / `LEFT_HIT=Notepad` / ...）；被测 exe 路径由 `wm.exe_path()` 从仓库位置推导，`--exe` 可覆盖。`lib/wm.py` 提供：找宿主窗、GetWindowRect/ExtFrameBounds、样式读写、SetWindowPos/ShowWindow、z 序遍历、PrintWindow/屏幕截图（PIL）、WM_CLOSE 优雅关、Toolhelp 进程枚举、config.json 读写、PMv2 DPI、真实桌面目录。

## publish/

| 脚本 | 用途 |
|---|---|
| `publish.py` | 本地打包发布：WM_CLOSE 优雅关运行实例 → dotnet publish（复用 FolderProfile.pubxml）→ `publish\WindowMerger-<版本>-win-x64.exe`。`--version 1.2.3` 覆盖版本 |

## tests/（自动回归）

| 脚本 | 回归点（原名） |
|---|---|
| `run_test_flow.py` | 全流程：清理 → 开测试窗 → CLI 吸附 → 命中/矩形断言 → 还原置顶（RunTestFlow） |
| `cross_dpi_seam_test.py` | 跨 DPI 缝隙：96DPI mspaint 吸进 150% 宿主，子窗口可见缘与格子四边 ≤1px；左屏不在/非 100% 自动 SKIP（CrossDpiSeamTest） |
| `shortcut_create_test.py` | 快捷方式生成：mspaint 单侧 + UIA 点按钮，校验 .lnk 参数含 `--left/--left-exe` 完整路径；mspaint 被占 SKIP 不强杀（ShortcutCreateTest） |
| `launch_attach_test.py` | 拉起吸附：目标未运行，宿主带 `--left 名字 --left-exe 完整路径` 启动，断言宿主自己拉起并吸附成功（LaunchAttachTest） |
| `orphan_e2e_test.py` | 孤儿清理端到端：强杀宿主留孤儿 → 重启宿主启动清理摘除 TOOLWINDOW（OrphanE2ETest） |
| `pid_mode_test.py` | CLI PID 模式：PID/名字混合吸附 + 无窗口 PID 的报因路径（PidModeTest） |
| `release_test.py` | 释放路径：UIA 点释放按钮，子窗口摘 TOOLWINDOW 且窗口完好（ReleaseTest） |
| `exclude_self_test.py` | 排除自身：另一个 WindowMerger 实例的宿主不可被 CLI 吸附（ExcludeSelfTest） |
| `cursor_drop_test.py` | 光标落点判定：光标在格外/窗口中心在格内 → 不吸附（旧中心逻辑回归）（CursorDropTest） |
| `ghost_cycle_test.py` | 吸附/释放循环的幽灵任务栏按钮检查（UIA + 窗口枚举）（GhostCycleTest） |
| `alt_tab_z_repro.py` | Alt+Tab 切回宿主后子窗口 z 序自愈回归（z 链探针，真实 Alt+Tab 注入）（AltTabZRepro） |

## manual/（人工交互验证）

| 脚本 | 用法（原名） |
|---|---|
| `manual_drag_test.py` | 最大化拖顶条还原：准备环境 + 每 150ms 采样时间线，**人工拖动**后按 ENTER 打判定（ManualDragTest） |
| `covered_drag_test.py` | 遮挡格拒收：置顶红色遮罩盖右格，**人工两步拖拽**（拖遮挡格=拒收，拖空格=吸附）（CoveredDragTest） |

## visual/（视觉验证，截图判定人工看）

| 脚本 | 验证点（原名） |
|---|---|
| `theme_menu_test.py` | UIA 开主题菜单、逐项选择，校验配置值与 ✓ 标记（纯 UIA，锁屏可用）（ThemeMenuTest） |
| `theme_toggle_visual_test.py` | UIA 切深/浅色各截一张对比（ThemeToggleVisualTest） |
| `theme_menu_shot.py` | 真实点击截展开的主题菜单（ThemeMenuShot） |
| `tooltip_shot.py` | 悬停主题按钮截 Tooltip 弹层 + 像素采样（Tooltip 是独立弹窗，必须全屏截）（TooltipShot） |
| `hover_visual_test.py` | 悬停分隔条/关闭/最大化/移开逐个截图（强制深色）（HoverVisualTest） |
| `divider_hover_test.py` | 分隔条悬停高亮竖条截图 + 取色（DividerHoverTest） |
| `hint_pane_shot.py` | 空格占位提示：空格填充+文案，吸附后该侧消失恢复透明（HintPaneShot） |
| `glyph_verify.py` | 内嵌 FA 字形渲染验证（PrintWindow，z 序免疫）（GlyphVerify） |
| `icon_verify.py` | exe 内嵌图标 + 运行中任务栏图标验证（IconVerify） |
| `pick_btn_dump.py` | 选窗按钮字形码点 dump + 4x 放大截图（PickBtnDump） |
| `side_btn_shot.py` | 顶条右侧按钮区截图（SideBtnShot） |
| `top_bar_left_shot.py` | 顶条左侧图标+标题截图（TopBarLeftShot） |

## utils/（单项工具）

| 脚本 | 用途（原名） |
|---|---|
| `atomic.py` | 置顶+截图+自动还原置顶（排查遮挡；截图后必须还原层级）（Atomic） |
| `shot.py` | 全屏/区域截图存 PNG（Shot） |
| `zoom_png.py` | PNG 区域放大（检字形/像素）（ZoomPng） |
| `rect.py` | 按 hwnd/标题查窗口矩形（Rect） |
| `hit.py` | 查某点 WindowFromPoint 命中（窗口标题/类/PID）（Hit） |
| `win_cmd.py` | 按 hwnd 执行 minimize/restore/close（WinCmd） |
| `drag.py` | 注入式拖动（受前台锁干扰，不可靠，回归别走这条）（Drag） |
| `z_dump.py` | 只读 z 序 dump（宿主/子窗口相邻关系）（ZDump） |
| `state_probe.py` | 全状态探针：宿主/子窗口/命中/前台（StateProbe） |
| `divider_probe.py` | 分隔条处命中探针（验证宿主盖住子窗口隐形边）（DividerProbe） |
| `attach_check.py` | 吸附状态确定性校验（TOOLWINDOW + 矩形，无屏幕探针）（AttachCheck） |
| `instance_times.py` | 列出运行中宿主实例启动时间（InstanceTimes） |
| `close_host_only.py` | 只优雅关 WindowMerger（WM_CLOSE，不动其他应用）（CloseHostOnly） |
| `close_instance.py` | 优雅关宿主 + 强杀测试窗（重建 exe 前清理）（CloseInstance） |
| `set_theme.py` | 改 config.json 主题（Auto/Dark/Light）（SetTheme） |
| `restore_theme.py` | 主题恢复 Auto（RestoreTheme） |
| `reset_ratio.py` | 分隔比例复位 0.5（ResetRatio） |
| `orphan_rescue.py` | 孤儿扫描/救援：扫描全部 TOOLWINDOW 孤儿，`--rescue --proc-name xxx` 摘样式+拉回屏（OrphanRescue） |

## archive/（一次性历史脚本，PowerShell 留档不维护；ASCII-only）

| 脚本 | 备注 |
|---|---|
| `AltTabRepro.ps1` | 真实 Alt+Tab 输入复现（z 序 bug 排查期产物，被 `tests/alt_tab_z_repro.py` 取代） |
| `NotepadPidDiag.ps1` | Win11 记事本单实例 PID 诊断（stub 交接排查期产物） |
| `BaselineShot.ps1` / `EdgeCompare.ps1` | 隐形边调查期基线截图/边缘扫描对照 |
| `VisualCheck2.ps1` | PrintWindow 宿主截图（被 `utils/` 截图系列覆盖） |
| `GenIco.ps1` | 生成多尺寸 .ico（图标已入库 `assets/`；改图标时再用，注意默认输出路径是旧仓库位置需改参） |
