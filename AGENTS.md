# AGENTS.md — WindowMerger 项目约定

把任意两个独立窗口合并进同一个带边框宿主窗口（透明格子 + 子窗口吸附，**不用 SetParent**）。
技术栈：C# WPF，`net10.0-windows`，单项目（`WindowMerger.csproj`，入口 `src/App.xaml`，宿主视觉树与布局尺寸常量在 `src/HostWindow.xaml`——`x:Name` 生成字段供 code-behind 引用，动态逻辑在 `HostWindow.cs` 与两个 partial（`HostWindow.Drag.cs` 交互拖拽 / `HostWindow.Attach.cs` 吸附编排）；构造顺序 = InitializeComponent → 配置尺寸覆盖（W/H/位置，只碰窗口自身、不碰 XAML 布局常量）→ WireUi（事件挂接 + 从 UI 读入布局尺寸 + 动态字形）→ ApplyTheme（换主题资源，XAML 只带深色初值）；窗口级事件（LocationChanged/StateChanged/Activated/250ms 定时器）在构造函数挂，WireUi 只挂 UI 元素）。
吸附态封装在 `src/AttachedChild.cs`（Hwnd/吸附前矩形 + 全部自身 hwnd 的 Win32 操作：`Attach` 捕获、`PlaceInPane` 放置含隐形边现场实测外扩与已就位跳过、`PrepareForDock`/`Undock`/`Restore`、`EnsureDockedState`、`MoveBy`/`MoveOffscreen`/`PlaceBelowHost`），与左右/几何/UI 完全解耦、可在格间整体交换；构造时持有宿主句柄（子窗口插入点 = 宿主正下方）。宿主以 `_left/_right` 两个引用持有，`SwapSides` = 引用交换。几何计算与吸附编排（TryAttach 分支、格子矩形、FixZOrder 遍历）留在宿主。
**布局尺寸单一来源 = XAML**（`_outer` BorderThickness / `_topBar` Height / 分隔条列宽），WireUi 读入 `_borderW/_topBarH/_dividerW` 字段，几何公式用字段；不能直接把 BorderThickness 当基准读——最大化时会写 0，恢复时形成循环（曾因此设计过分步写回）。最小窗口尺寸 = XAML `MinWidth/MinHeight`（WndProc 的 ptMinTrackSize 读它们）。
主题刷色 = **换窗口资源**：`HostWindow.Resources` 里 7 个 `Theme*Brush` 键，元素一律 `DynamicResource` 引用，`ApplyTheme` 只替换资源值；**悬停刷色也在 XAML**（Button 隐式样式/DangerCaptionButton/DividerStyle 的 `IsMouseOver` Trigger + DynamicResource，实测 .NET 10 WPF 完全可用——早前"Trigger 不能用 DynamicResource"的记录是错误结论）。**陷阱**：对 DynamicResource 属性做局部赋值（如事件里刷悬停色）会销毁资源引用表达式，之后 `ClearValue` 不会恢复引用而是落到 null（实测分隔条变透明）——悬停一律走 Trigger，不要用事件刷色。顶条按钮是 XAML 实例 + 隐式 Button 样式，静态字形直接写在按钮文本里，点击/动态字形（主题月亮/太阳/半圆、最大化还原、左右选窗按钮的方向/空格字形）由 WireUi/UpdateSideButtons 补。

## 构建 / 运行 / 提交

```cmd
dotnet build -c Release        :: 必须做到 0 警告 0 错误
bin\Release\net10.0-windows\WindowMerger.exe [左进程名|左PID 右进程名|右PID]
bin\Release\net10.0-windows\WindowMerger.exe --left Code --right ZCode
bin\Release\net10.0-windows\WindowMerger.exe --left 12345 --right mspaint
```

- **重建前必须先关闭运行中的实例**（exe 被运行实例锁定会构建失败）。优雅关闭 = PostMessage `WM_CLOSE (0x0010)`，走正常退出流程（保存配置 + 释放子窗口回原位）；`taskkill /F` 会跳过这些清理，仅在卡死时用
- 功能迭代单独 commit；`bin/`、`obj/`、`publish/`、`.zcode/` 已在 .gitignore，勿入库
- 发布：本地 `py tools\publish\publish.py`（自动 WM_CLOSE 优雅关运行实例 → 复用 `Properties\PublishProfiles\FolderProfile.pubxml`（打包设置唯一来源，VS 发布对话框里改、脚本与 CI 自动跟随）→ copy 改名替换产出 `publish\WindowMerger-<版本>-win-x64.exe`，版本默认取 csproj、`--version` 可覆盖，产物为框架依赖单文件 exe、目标机器需 .NET 10 Desktop Runtime x64）；推 `v*` tag 或在 Actions 页手动触发 `.github/workflows/release.yml` 发 GitHub Release（tag 版本去 `v` 写程序集版本；dispatch 填 `version` 直接在所选分支 HEAD 自动建 tag 发版、可勾 prerelease，留空仅构建出工件不发 Release）；main 分支每次 push 自动打包并发 prerelease Release（挂在固定滚动 tag `nightly` 上，先删旧 Release 再把 tag 强制挪到该提交重发，不新增 tag），CI 产物为 zip（内含固定名 `WindowMerger.exe`，不随版本改名），版本号 `0.0.1.<提交hash前8位>` 体现在 zip 文件名与 Release 标题；**带 hash 的版本不能直接喂 `-p:Version`**——NuGet restore 把 `$(Version)` 当 PackageVersion 校验，第 4 段非数字即拒收（报“不是有效的版本字符串”，实测炸在 restore 阶段且 MSB4181 无具体日志），CI 与 publish.py 同款拆法：`-p:Version=<数字前缀>` + `-p:InformationalVersion=<显示版本>`（后者进 exe 的 ProductVersion）

## 本仓库踩过的真坑（违反必炸，全部实测）

### P/Invoke（LibraryImport 源生成器）
- **不会自动补 W 后缀**：自定义方法名必须显式 `EntryPoint` 指向真实导出名。已为此崩过三次：`GetMonitorInfoW`、`GetWindowTextLengthW`、`DwmSetWindowAttributePointer→DwmSetWindowAttribute`。新增 P/Invoke 时先确认真实导出名
- **不支持 `StringBuilder` 参数**：字符串出入参走经典 `DllImport`（CharSet.Unicode）——**漏写 CharSet 按 ANSI 反序列化**：原生端写 WCHAR、size 返回字符数，ANSI marshaller 遇伪空字节提前截断 → `sb.Length < size` → `ToString(0, size)` 越界崩宿主（实测 QueryFullProcessImageNameW 三连崩，2026-11）
- `dwmapi` 属性 `DWMWA_FORCE_ICONIC_REPRESENTATION` **只写不可读**（Get 返回 E_INVALIDARG）——不要用读回验证它

### WPF / Win32 语义
- `SetWindowPos` 的 `hWndInsertAfter` = "放到目标窗口**下方**"。子窗口吸附 z 序 = 子窗口永远插在宿主**正下方**（宿主不透明部分盖住子窗口隐形边，分隔条才可点击；透明格子透出子窗口）
- **拉起子窗口 z 序不要用 `HWND_TOP`**：Alt+Tab 切回宿主后它是**静默无效调用**（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住，实测必现）；z 序修复一律相对插入 `hWndInsertAfter = 宿主`，自愈校验用"宿主正下方连续子窗口块"（见 `FixZOrder`）。复现/回归：`tools\tests\alt_tab_z_repro.py`
- 吸附子窗口设为 `WS_EX_TOOLWINDOW`（无任务栏/Alt+Tab）→ **最小化或独立最大化后无法手动恢复**，维护定时器（250ms）会自动拉回：子窗口没有"自己最大化"的概念
- Win11 DWM 自动圆角是格子四角"圆角缝"的根源：吸附时设 `DWMWA_WINDOW_CORNER_PREFERENCE=DONOTROUND`，释放还原 `DEFAULT`
- 带框窗口有 ~7px 隐形边（`GetWindowRect` > 可见窗口）：吸附矩形按 `DWMWA_EXTENDED_FRAME_BOUNDS` 实测外扩，可见内容才与格子齐平
- **隐形边是物理像素且随所在显示器 DPI 缩放**（实测 mspaint：7px@100% ↔ 9px@150%，4K+100% 双屏）——吸附时**缓存** `FrameMargins` 会在跨屏吸附/宿主拖过另一块屏/改系统缩放后失真，可见内容缩水 2~4px，透明格透出后面的桌面形成整条竖缝/底缝（且 ±1px 就位跳过用的也是同一份失真值，维护定时器永远无法自愈，4K 屏实测）。因此 `PlaceInPane` 必须**每次放置现场实测**（`GetInvisibleFrameMargins` 一次 = GetWindowRect + 一次 DwmGetWindowAttribute，250ms 定时器开销可忽略）；DPI 切换瞬间子窗口还会收到 `WM_DPICHANGED` 自己改尺寸，下一个维护周期收敛
- **1 DIP 边框在 150% 缩放下 = 1.5 物理px，非整数设备像素抗锯齿出半透明发丝线**（4K 屏实测）——细边框一律取 ≥2 DIP 保证整数物理像素（窗格边框因此 `1,2,1,1` → 统一 `2`）；几何上窗格边框加宽无副作用：`PaneRectDevice` 不读它，子窗口外扩时本来就压在边框线下面、由宿主盖住
- **任务栏图标按本征尺寸绘制、shell 不放大**：图标画布必须取 `GetSystemMetrics(SM_CXICON/SM_CYICON)`（PMv2 进程随 DPI：32px@100% ↔ 48px@150%），固定 32px 画布在 4K 上比周边应用小一圈（实测）。另 `WM_GETICON`/`GetClassLong` 返回的是子窗口**自有**图标句柄（非副本），绝不能 `DestroyIcon`（会毁掉子窗口自己的图标）
- **宿主格子区域 alpha=0 在 OS 层点击穿透**（分层窗口全透明像素，拖入吸附因此走全局 WinEvent+光标坐标而非 WPF 鼠标事件）。推论：`WindowFromPoint(光标)` 在格子处返回的是宿主**后面**的窗口，"光标处最顶层是否本宿主"不能直判——必须用 z 序走到宿主为止的遍历、跳过被拖窗口与 `WS_EX_TRANSPARENT` 穿透层（`IsCoveredAtCursor`），直判会把拖入空格子（吸附主入口）误杀。**空格与吸附格的透明性是按占位切换的**：空格以 ThemeBar 填充+提示文案（不穿透，`UpdatePaneHints`）；**吸附格必须回到透明**——子窗口靠透明格子透出、点击穿透下去交互，填实会废掉吸附应用的交互
- UIPI：管理员权限窗口（如任务管理器）**无法**被普通权限程序吸附，`SetWindowPos` 静默失败——失败时必须状态回滚 + 状态栏报因
- 分隔条/格子几何一律用窗口 `ActualWidth` 直算，**不要读 `_content.ActualWidth`**（StateChanged 早于尺寸回缩完成，旧值会把分隔条顶偏）
- **窗口几何持久化 = 正常态矩形物理像素 + 是否最大化**（config.json WinLeft/Top/Right/Bottom/WinMaximized）：存时 DIP × 关闭时窗口所在屏 DPI（最大化/最小化关闭取 RestoreBounds），恢复按目标屏 DPI 换算并钳制到最近可见显示器工作区（`MonitorFromPoint(NEAREST)` + `GetDpiForMonitor`）——DIP 直存会跨屏漂移，跨屏拼接会存出超屏值。**WPF 在 hwnd 建好前设 Left/Top/Width/Height 一律按初始主屏 DPI 解释**（跨屏落位漂移/被居中覆盖，实测）——跨屏落位必须在 `OnSourceInitialized` 用 `SetWindowPos` 写物理像素，且**两步走**：先移动触发 WM_DPICHANGED 收敛目标屏缩放、再设尺寸（WPF 跨 DPI 保 DIP 不保物理，一步到位会被改写，实测 S1 场景）；测试脚本起的宿主一律 `SetWindowPos` 缩小并停到左侧 100% 屏，别占用户 4K 主屏
- **强杀宿主 = 孤儿**：吸附子窗口残留 `WS_EX_TOOLWINDOW`（任务栏消失，宿主最小化期间被强杀还会停在屏幕外 -32000）。孤儿清理必须**按配置记录的 HWND 精确匹配**（PID 仅作句柄复用校验），**绝不能按 PID 枚举该进程全部窗口**——进程的隐藏辅助窗口（`CiceroUIWndFrame` 等，实测 opera/Listary/RepositoryTree 都带 TOOLWINDOW）会被误显示成"点不出来的任务栏幽灵按钮"。吸附成功立即 SaveConfig 落盘（强杀时才有记录可循）。救援 `tools\utils\orphan_rescue.py`，回归 `tools\tests\orphan_e2e_test.py`

### 字体与资源（Font Awesome Free，SIL OFL；全部内嵌进程序集）
- 字体/图标在 `assets\`，以 `<Resource>` 内嵌（csproj），输出目录不落散资源文件
- **pack 字体必须经 XAML 声明**：`HostWindow.Resources` 里 `<FontFamily x:Key="FaSolid">pack://application:,,,/assets/<文件>#<完整家族名></FontFamily>`（FaRegular 同款）——这是唯一渲染正常的路径。**代码里 `new FontFamily(同样的 pack 字符串)` 能构造、GetResourceStream/GetFontFamilies 都正常，但 DWrite 渲染不解析（全部回退缺字）**——.NET 10 WPF 实测，别再试
- 无需运行时加载/校验代码：XAML 声明即渲染（字形直接写在按钮文本里，动态字形由 code-behind 切 Content）
- ico 内嵌后用 `BitmapDecoder.Create(资源流)` 解码取最大帧

### .NET 10 WPF 特有
- **Window 基类自带实验性 `ThemeMode` 属性**——自定义类名避开 `Theme`/`ThemeMode`（本项目用 `AppTheme`/`AppThemeMode`）

## 源码修改纪律

- **禁止用 PowerShell 正则批量改源文件**：PS 5.1 按系统 ANSI（GBK）读 UTF-8 文件，中文源文件会整文件乱码损毁（本次 HostWindow.cs 曾因此整体重写）。源码修改只用 Edit 工具
- **tools 脚本 = Python 3.14**（`tools\lib\wm.py` 公共库：ctypes Win32/截图/进程/config；`wm_uia.py`：comtypes UIA；依赖 `py -m pip install pillow comtypes`；脚本一律 `sys.path.insert(0, .../lib)` 后 `import wm`，调用 `py tools\<目录>\<脚本>.py`）。中文注释可用（lib 已重配 stdout UTF-8）；诊断输出标记保持英文（NO_HOST / LEFT_HIT=...）。仅 `tools\archive\*.ps1` 是历史留档：内容 ASCII-only（PS 5.1 把 UTF-8 无 BOM 当 ANSI 读，中文会破坏解析），不再维护勿新增
- 注释与 UI 文案用中文；异常直接抛出，不吞（唯一例外：配置文件损坏回退默认值、UIPI/DWM 属性调用失败按设计降级）

## 运行环境注意（Bash 工具 = CMD）

- 无 POSIX 命令（`ls`/`grep`/`timeout` 均不可用）；延时用 `ping -n N 127.0.0.1 >nul`
- PowerShell 内联单行命令经 CMD 双层转义极易损坏（`$null` 转义、嵌套表达式不展开、中文参数变乱码）——**复杂逻辑一律写 `tools\*.py` 脚本文件**再执行，参数传数字/ASCII；本仓库 Bash 工具实为 Git Bash（无 `%TEMP%` 展开，用 `$TEMP`/POSIX 路径）
- **锁屏会话（前台 = LockApp）时注入点击/键盘全部落在锁屏上，GDI 全屏截图报"句柄无效"**——远程交互验证会静默失败。此时 UIA `InvokePattern` 仍可用（进程内直调 Click，不走输入注入），可作为替代验证路径（见 `tools\visual\theme_menu_test.py`）
- 验证脚本截图后**必须还原层级**（`HWND_NOTOPMOST`），不得给用户正在运行的实例残留置顶
- Python 工具链实测坑（2026-11 转换期）：`SystemParametersInfoW(SPI_GETWORKAREA)` 本机 Win11 直接失败（err=0），主屏工作区用 `MonitorFromPoint(NEAREST)+GetMonitorInfo`；`SHGetKnownFolderPath` 第一参数是 **GUID 结构体指针**，传字符串地址不报错但返回未重定向的默认路径（本机桌面重定向 D:\Users）；psapi `GetModuleBaseNameW` 受限句柄查不到提权进程名，进程名一律 Toolhelp 快照；comtypes 1.4.17 对 UIAutomation typelib 生成的桩在 Python 3.14 上退化为 Incomplete（GetCurrentPattern 返回 NULL），UIA 层用 `uiautomation` 包；**打包应用（WindowsApps）进程 StartTime 不可靠**（预创建/挂起唤醒可早于宿主启动），"宿主拉起"判定用父进程链（`wm.launched_by`，stub→后代两层）；`shot.py` 的负坐标参数会被"未指定"哨兵吞掉（原 PS 同款语义），负坐标区域直接调 `wm.capture_screen`

## 验证流程

- **清理/回归脚本会无差别关闭所有 WindowMerger/Notepad/mspaint——包括用户自己开着的实例**（Notepad 是 Stop-Process 强杀，未保存内容丢失）。跑之前先确认没有正在使用的窗口，这是实测踩过的坑
- 全流程回归：`py tools\tests\run_test_flow.py`（清理 → 开测试窗 → CLI 吸附 → 命中/矩形偏差 → 还原置顶状态）
- 跨 DPI 缝隙回归（4K+100% 双屏）：`py tools\tests\cross_dpi_seam_test.py`（96DPI mspaint 吸附进 150% 宿主，断言子窗口可见缘 ExtFrameBounds 与格子矩形四边 ≤1px；左侧显示器不在/非 100% 时 SKIP）
- 快捷方式生成回归：`py tools\tests\shortcut_create_test.py`（mspaint 单侧 + UIA 点按钮校验 .lnk 含 --left/--left-exe 完整路径；**不起 notepad——用户要求测试窗一律 mspaint、窗口由其人工选择**，mspaint 被占用时 SKIP 不强杀）
- 拉起吸附回归：`py tools\tests\launch_attach_test.py`（关闭 mspaint → 宿主带 `--left 名字 --left-exe 完整路径` 启动 → 断言宿主自己拉起 mspaint 且吸附成功；打包应用真实路径现场用 QueryFullProcessImageNameW 解析、不硬编码版本号路径）
- 单项工具（`tools\utils\`）：`rect/hit/shot/drag/win_cmd/atomic.py`（atomic = 置顶+截图+自动还原置顶，用于排查遮挡问题）
- 拖动类交互（最大化拖动还原/遮挡格拒收等）用交互式脚本人工验证：`tools\manual\manual_drag_test.py`（环境准备 + 每 150ms 采样打印时间线）、`tools\manual\covered_drag_test.py`（置顶遮罩盖右格，两步人工拖拽出判定）——注入式自动拖动受前台锁/覆盖窗干扰不可靠（实测反复 FAIL_COVERED），不要走回头路
- 主题/悬停类视觉验证：`tools\visual\tooltip_shot.py`（悬停截 Tooltip 弹层 + 像素采样对调色板；**Tooltip 是独立弹窗，必须 CopyFromScreen 全屏截屏，PrintWindow 只能截宿主自己**）、`tools\utils\zoom_png.py`（PNG 区域放大，检字形/像素）、`tools\visual\theme_menu_shot.py`（真实点击截展开的主题菜单）
- CLI 吸附验证的顺序：**先启动目标窗口，再带参启动宿主**（吸附发生在宿主 Loaded 时，目标必须已存在）。参数**纯数字 = PID、否则 = 进程名**；PID 三级回退：精确 PID → 后代进程树（Win11 打包应用经别名 stub 启动，`Start-Process -PassThru` 返回的 stub 没有窗口，真实窗口属于其后代进程，Toolhelp 快照走树匹配）→ 同名进程（stub 已退出的交接场景兜底）
- Win11 记事本是单实例多标签：同名目标会去重只吸一个，属预期
- 悬停任务栏弹窗的远程截图时机不稳定，最终视觉验收交给用户

## 已知边界（不要试图"修复"）

- **永远不要把子窗口的截图绘制进宿主窗口**（用户明确的永久规则，违反 = 预览假修复 + 点击被宿主拦截）
- **不做自定义缩略图/预览接管（iconic 位图方案已于 2026-11 移除）**：DWM 对 `FORCE_ICONIC` 窗口的缩略图请求尺寸恒为 200x109（不随 Alt-Tab 瓦片大小变化）、超尺寸位图 `E_INVALIDARG` 拒收、显示不放大——吸附态 Alt-Tab 瓦片无法铺满，无 API 可突破；而取消 FORCE 后宿主实时渲染只有顶条+透明格子（空面板），信息量更差。当前行为：任务栏/Alt+Tab 显示宿主实时画面（顶条 + 深色空格子），属已知取舍
- Alt+Tab/任务栏只显示宿主一项（子窗口 tool window 是吸附架构的一部分）
- 最大化时外边框隐藏（`CurBorderW`=0）、子窗口铺满格子，属设计
- 分隔条拖到极端比例时，右格可能窄于目标应用的最小宽度（如 mspaint ≈704px）——OS 钳制缩放，子窗口会探出宿主右缘约数十像素，非 bug
