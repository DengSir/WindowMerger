# tools 脚本清单

开发/验证/发布脚本，**Python 3.14**（公共库 `lib/wm.py` ctypes Win32 封装 + `lib/wm_uia.py` UIA），调用方式 `uv run tools/<目录>\<脚本>.py`。全量对照（原名 → 新位置）：

| 目录 | 用途 | 数量 |
|---|---|---|
| `run_all.py` | **一键完整回归**：按依赖顺序跑全部自动测试 + 汇总表（`--only` 子集 / `--list` 清单），44 项全覆盖（32 tests + 12 visual） | 1 |
| `publish/` | 本地打包发布 | 1 |
| `tests/` | 自动回归测试（自动清理/还原，可无人值守跑） | 32 |
| `diag/` | 一次性诊断探针（bug 排查期产物，留档复用；非常驻回归） | 24 |
| `targets/` | 测试靶窗（tkinter/ctypes 受控窗口，供 tests 拉起） | 5 |
| `manual/` | 人工交互排查工具（对应场景已有自动版在 tests/，此处留作诊断） | 2 |
| `visual/` | 视觉/主题/字形/截图验证——**12 个带自动判定已入 run_all**，theme_menu_shot 出 PNG 兼断言 | 12 |
| `utils/` | 单项工具：查询/控制/截图/配置/CI | 24 |
| `archive/` | 一次性历史脚本（**PowerShell 留档，不再维护**） | 6 |
| `lib/` | 公共库：`wm.py`（ctypes Win32/截图/进程/config/调色板）、`wm_uia.py`（uiautomation UIA） | 2 |

**依赖**：[uv](https://docs.astral.sh/uv/) 自动管理——`uv run` 首次执行按根目录 `pyproject.toml`/`uv.lock` 自动建 `.venv` 并装依赖（pillow 截图、uiautomation/comtypes UI Automation），无需手动 pip。应用本身不需要 Python。

**拖动类测试约定（2026-11 实测固化）**：除 `geometry_persistence_test`（恢复定位即被测对象）外，一律**固定布局**——宿主与靶窗口先 `SetWindowPos` 钉到主屏固定矩形（主屏上坐标=物理像素，无跨 DPI 换算地雷）再操作；靶窗口用 **mspaint**（Win11 notepad 自我缩放/最小尺寸钳制不可靠，用户确认）；拖动抓点取**标题栏中点**（左侧图标抓不动、右侧有按钮）；窗口尺寸一律以**钉位后回读值**推导（PMv2 窗口会被按 DPI 缩放，写死值不可信）。

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
| `release_test.py` | 释放路径：UIA 点释放按钮，子窗口摘 TOOLWINDOW 且窗口完好（ReleaseTest） |
| `picker_attach_test.py` | 顶条选窗吸附全链路：UIA 点 ← → 选窗对话框过滤/选中/吸附 → 左格断言（新增 2026-11） |
| `swap_sides_test.py` | 交换左右：UIA 点交换按钮 → 两侧命中互换断言（新增 2026-11） |
| `geometry_persistence_test.py` | 几何持久化四场景：保存/恢复、最大化保存/恢复、屏外钳制、垃圾回退（新增 2026-11，首次脚本化 ef15752 的手工验证） |
| `cross_dpi_seam_test.py` | 跨 DPI 缝隙：96DPI mspaint 吸进 150% 宿主，子窗口可见缘与格子四边 ≤1px；左屏不在/非 100% 自动 SKIP（CrossDpiSeamTest） |
| `shortcut_create_test.py` | 快捷方式生成：mspaint 单侧 + UIA 点按钮，校验 .lnk 参数含 `--left/--left-exe` 完整路径；mspaint 被占 SKIP 不强杀（ShortcutCreateTest） |
| `launch_attach_test.py` | 拉起吸附：目标未运行，宿主带 `--left 名字 --left-exe 完整路径` 启动，断言宿主自己拉起并吸附成功（LaunchAttachTest） |
| `orphan_e2e_test.py` | 孤儿清理端到端：强杀宿主留孤儿 → 重启宿主启动清理摘除 TOOLWINDOW（OrphanE2ETest） |
| `pid_mode_test.py` | CLI PID 模式：PID/名字混合吸附 + 无窗口 PID 的报因路径（PidModeTest） |
| `exclude_self_test.py` | 排除自身：另一个 WindowMerger 实例的宿主不可被 CLI 吸附（ExcludeSelfTest） |
| `cursor_drop_test.py` | 光标落点判定（注入拖动，固定布局）：光标在格外/窗口中心在格内 → 不吸附；拖到左格中心 → 吸附（CursorDropTest） |
| `covered_drag_test.py` | 遮挡格拒收（自动化）：置顶遮罩盖右格，注入拖到遮罩内 → 拒吸；拖到左格 → 吸附（原 manual/CoveredDragTest 自动化，2026-11） |
| `maximize_drag_test.py` | 最大化拖顶条还原（自动化）：最大化 → 注入拖顶条 → 还原落位=占比锚点公式期望值（原 manual/ManualDragTest 自动化，2026-11） |
| `double_click_max_test.py` | 双击顶条最大化/再双击还原（新增 2026-11；最大化后顶条坐标须按当前矩形重算） |
| `divider_resize_test.py` | 拖分隔条调比例（子窗口矩形跟随）+ 双击复位 0.5 + 关闭后 config Ratio 校验（新增 2026-11） |
| `minimize_linkage_test.py` | 最小化联动：宿主最小化子窗口移出屏外 -32000、还原拉回格子（新增 2026-11） |
| `drag_switch_side_test.py` | 拖到另一侧换侧（新增 2026-11；**挖出并修复 src 换侧分支引用反向 + TryAttach 拒收 toolwindow 两个真 bug**） |
| `ghost_cycle_test.py` | 吸附/释放循环的幽灵任务栏按钮检查（UIA + 窗口枚举，含死应用陈旧按钮判定）（GhostCycleTest） |
| `alt_tab_z_repro.py` | Alt+Tab 切回宿主后子窗口 z 序自愈回归（z 链探针，真实 Alt+Tab 注入）（AltTabZRepro） |
| `topbar_state_test.py` | 顶条状态回归：最大化矩形=工作区（WM_GETMINMAXINFO）、最大化顶条原地单击不还原、空吸附快捷方式通知、侧按钮字形翻转（TopbarStateTest） |
| `max_top_drag_test.py` | 最大化顶边死区拖还原：WM_NCHITTEST 最大化整窗 HTCLIENT 逐行探针 + 顶边注入拖还原（MaxTopDragTest） |
| `child_fg_raise_test.py` | 子窗口激活联动升顶：EVENT_SYSTEM_FOREGROUND → 宿主升顶 + 子窗口粘回，净空校验 GA_ROOT（ChildFgRaiseTest） |
| `attach_heal_test.py` | 自愈与释放全量语义：外部最大化拉回、子窗死亡格子清空、释放矩形逐像素回位+摘置顶、单侧交换、H7 外部隐藏自动释放、H8 真托盘链路、H5E 释放拉回前台（AttachHealTest） |
| `pane_drag_rules_test.py` | 格子拖入规则：占用格拒绝/Ctrl 替换/拖出自愈/宿主拖动子窗跟随（PaneDragRulesTest） |
| `picker_filter_test.py` | 选窗候选过滤：负向过滤（toolwindow/owned/排除类名）、大小写不敏感、未选中点吸附无操作（PickerFilterTest） |
| `config_edge_test.py` | 配置边界：损坏 JSON 回退默认、Ratio 钳制、几何过小钳 MinWidth/MinHeight、非法 Theme 回退（ConfigEdgeTest） |
| `cli_args_test.py` | CLI 参数边界：位置参数≡命名参数、缺参/未知旗标报因、大小写/.exe 后缀、找不到的报因文案（CliArgsTest） |
| `pid_fallback_test.py` | PID 三级回退后两级：后代进程树 + 同名兜底 + 面积最大（PidFallbackTest） |
| `snap_capture_test.py` | snap 捕捉接管 e2e：检测命中/比例、接管双吸附、拼图图标、宿主矩形=工作区、释放回捕获矩形、profile 隔离、报因四场景、托盘单实例（SnapCaptureTest） |
| `update_e2e_test.py` | 自动更新 e2e：假 releases/latest → 自动弹框 → 下载换装重启全链（UpdateE2ETest） |
| `update_edge_test.py` | 更新边界：版本前缀解析/404/开关持久化/坏 zip 保留/.old 占用自愈（UpdateEdgeTest） |

## diag/（一次性诊断探针，bug 排查期产物留档）

| 脚本 | 排查对象 |
|---|---|
| `snap_detect_dump.py` | snap 检测逐屏逐窗判据对照（定位 NO_LAYOUT 卡在哪条判据） |
| `snap_hdpi_repro.py` | 高 DPI 屏捕捉/接管 e2e 复现（ctypes Win32 靶窗；等待期必须泵本进程消息） |
| `snap_restore_probe.py` | 接管宿主最大化/还原路径矩形观测 |
| `snap_align_probe.py` | 靶窗 EFB 对齐逐轮差值（跨 DPI 屏界不收敛实锤） |
| `efb_boundary_probe.py` | EFB 跨 DPI 屏界读数一致性（排除 EFB 虚拟化假说） |
| `dblclk_restore_probe.py` | 双击还原逐 100ms 时间线采样（还原竞态排查） |
| `topbar_overlay_test.py` | 最大化顶条 overlay 显隐可视化验证（子窗占满全高/滑入滑出截图） |
| `border_probe.py` | 隐形边/边框测量（NORMAL/MAXIMIZED/跨 DPI） |
| `divider_seam_test.py` / `divider_seam_diff.py` | 分隔条缝隙测量/像素对照 |
| `thirds_align_probe.py` | 三分靶窗对齐探针 |
| `trace_order_check.py` | WM_TRACE=1 时序打点检查（SourceInitialized→Loaded→吸附→图标顺序） |
| `corner_pref_test.py` | 圆角偏好探针（吸附态黑盒判定口径） |
| `attachable_probe.py` | 吸附资格探针（IsAttachable 判定逐窗核对） |
| `taskbar_button_probe.py` / `taskbar_hide_probe.py` | 任务栏按钮收录/隐藏探针 |
| `host_icon_probe.py` / `exe_icon_fallback_probe.py` / `iconless_fallback_check.py` | 宿主图标管线/exe 图标兜底/无图标窗兜底检查 |
| `ico_format_probe.py` / `icon_map_probe.py` | ico 资源解码/图标映射探针 |
| `snap_uwp_icon_check.py` / `store_paint_icon_probe.py` / `system_windows_icon_probe.py` | UWP/商店/系统窗口图标素材检查 |

## targets/（测试靶窗）

| 脚本 | 用途 |
|---|---|
| `drag_target.py` | 拖动测试靶窗（零 Ribbon/零 DPI 感知声明，标题几何已知） |
| `snap_target.py` | snap 检测/接管靶窗（单进程单顶层无 owner 窗） |
| `multi_win.py` | 一进程两窗靶（PID 后代树回退测试） |
| `tray_target.py` | 托盘行为靶窗（收 WM_CLOSE 自我 withdraw 不销毁，模拟微信关闭到托盘） |
| `color_pad.py` | 纯色窗（视觉验证靶） |

**visual/ 中已入 run_all 的自动判定测试**（调色板期望值见 `lib/wm.py` PALETTES）：

| 脚本 | 自动断言 |
|---|---|
| `theme_menu_test.py` | UIA 逐项选 深色/浅色/恢复，校验 config Theme（自定义 Header 的 MenuItem UIA Name 为空，只能按索引 Invoke） |
| `theme_toggle_visual_test.py` | UIA 切浅/深色，顶条像素 = 调色板 Bar 色 + 配置持久化 |
| `tooltip_shot.py` | 悬停主题按钮（UIA 取真实按钮矩形定位，写死偏移会落到别的按钮）Tooltip 底色 = Bar 色，深浅各一轮 |
| `hover_visual_test.py` | 分隔条悬停蓝/基态灰、最大化悬停灰（采样取按钮顶部无字形区）、关闭悬停红 |
| `divider_hover_test.py` | 分隔条 基态/悬停/移开 三态像素（snap 探针不得动光标，否则全变悬停色——原 PS 缺陷） |
| `hint_pane_shot.py` | 空格填充=Bar 色、吸附断言成立（notepad 深色编辑器底色≈ThemeBar，"透出"不能靠像素比对）、右格填充保留 |
| `pick_btn_dump.py` | 顶条 9 个按钮 AutomationId→字形码点逐个比对（兼验证 FA 内嵌字体没缺字回退） |
| `glyph_verify.py` / `side_btn_shot.py` / `top_bar_left_shot.py` | 按钮区/标签区存在 ThemeText 色像素（字形/文字画出来了），PNG 人工复核 |
| `icon_verify.py` | exe 内嵌图标可提取 + 任务栏按钮存在；图标长相人工看 PNG |
| `theme_menu_shot.py` | 真实点击主题按钮 → 断言菜单弹出（≥3 MenuItem）+ 截图 |

**本质人工、不在 run_all**：UIPI 管理员窗口拒吸（需管理员靶窗）、跟随系统 WM_SETTINGCHANGE 实时刷（需切系统主题）、图标/字形美观度、悬停任务栏弹窗时机、`publish.py` 打包（日常回归不含发版）。

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
| `ci_status.py` / `ci_log_read.py` / `ci_log_fetch.py` / `ci_check.py` | GitHub Actions 运行状态/日志读取/拉取/检查（CI 排查） |
| `list_action_tags.py` | 列 GitHub Action 可用 tag（核对 setup-uv 等钉版） |
| `env_probe.py` | 运行环境探针（DPI/显示器/系统信息）（EnvProbe） |

## archive/（一次性历史脚本，PowerShell 留档不维护；ASCII-only）

| 脚本 | 备注 |
|---|---|
| `AltTabRepro.ps1` | 真实 Alt+Tab 输入复现（z 序 bug 排查期产物，被 `tests/alt_tab_z_repro.py` 取代） |
| `NotepadPidDiag.ps1` | Win11 记事本单实例 PID 诊断（stub 交接排查期产物） |
| `BaselineShot.ps1` / `EdgeCompare.ps1` | 隐形边调查期基线截图/边缘扫描对照 |
| `VisualCheck2.ps1` | PrintWindow 宿主截图（被 `utils/` 截图系列覆盖） |
| `GenIco.ps1` | 生成多尺寸 .ico（图标已入库 `assets/`；改图标时再用，注意默认输出路径是旧仓库位置需改参） |
