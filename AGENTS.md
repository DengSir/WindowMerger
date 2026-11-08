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
- 发布：本地 `uv run tools/publish\publish.py`（自动 WM_CLOSE 优雅关运行实例 → 复用 `Properties\PublishProfiles\FolderProfile.pubxml`（打包设置唯一来源，VS 发布对话框里改、脚本与 CI 自动跟随）→ copy 改名替换产出 `publish\WindowMerger-<版本>-win-x64.exe`，版本默认取 csproj、`--version` 可覆盖，产物为框架依赖单文件 exe、目标机器需 .NET 10 Desktop Runtime x64）；推 `v*` tag 或在 Actions 页手动触发 `.github/workflows/release.yml` 发 GitHub Release（tag 版本去 `v` 写程序集版本；dispatch 填 `version` 直接在所选分支 HEAD 自动建 tag 发版、可勾 prerelease，留空仅构建出工件不发 Release）；main push 只触发测试 workflow（`test.yml`），不发版；CI 产物为 zip（内含固定名 `WindowMerger.exe`，不随版本改名）；**带 hash 的版本不能直接喂 `-p:Version`**——NuGet restore 把 `$(Version)` 当 PackageVersion 校验，第 4 段非数字即拒收（报“不是有效的版本字符串”，实测炸在 restore 阶段且 MSB4181 无具体日志），CI 与 publish.py 同款拆法：`-p:Version=<数字前缀>` + `-p:InformationalVersion=<显示版本>`（后者进 exe 的 ProductVersion）

## 本仓库踩过的真坑（违反必炸，全部实测）

### P/Invoke（LibraryImport 源生成器）
- **不会自动补 W 后缀**：自定义方法名必须显式 `EntryPoint` 指向真实导出名。已为此崩过三次：`GetMonitorInfoW`、`GetWindowTextLengthW`、`DwmSetWindowAttributePointer→DwmSetWindowAttribute`。新增 P/Invoke 时先确认真实导出名
- **不支持 `StringBuilder` 参数**：字符串出入参走经典 `DllImport`（CharSet.Unicode）——**漏写 CharSet 按 ANSI 反序列化**：原生端写 WCHAR、size 返回字符数，ANSI marshaller 遇伪空字节提前截断 → `sb.Length < size` → `ToString(0, size)` 越界崩宿主（实测 QueryFullProcessImageNameW 三连崩，2026-11）
- `dwmapi` 属性 `DWMWA_FORCE_ICONIC_REPRESENTATION` **只写不可读**（Get 返回 E_INVALIDARG）——不要用读回验证它
- **快捷方式 .lnk 的 WScript.Shell 保存走系统 ANSI 代码页**：中文文件名前缀"窗口合并"在 en-US（CP1252）被转成字面 `????`（非法文件名字符）→ `Unable to save shortcut` 必败（CI 实测，zh-CN GBK 可编码故开发机从未暴露）——shortcut_create_test 按 `GetACP()≠936` SKIP；国际化修复（ASCII 回退文件名）待产品决定。**别走 IShellLinkW 内建 COM interop**：PS5.1/.NET 10 双环境实测 Set* 字符串方法一律 ArgumentException（原因未明），浪费两轮 CI

### WPF / Win32 语义
- `SetWindowPos` 的 `hWndInsertAfter` = "放到目标窗口**下方**"。子窗口吸附 z 序 = 子窗口永远插在宿主**正下方**（宿主不透明部分盖住子窗口隐形边，分隔条才可点击；透明格子透出子窗口）
- **拉起子窗口 z 序不要用 `HWND_TOP`**：Alt+Tab 切回宿主后它是**静默无效调用**（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住，实测必现）；z 序修复一律相对插入 `hWndInsertAfter = 宿主`，自愈校验用"宿主正下方连续子窗口块"（见 `FixZOrder`）。复现/回归：`tools\tests\alt_tab_z_repro.py`
- **子窗口所有 z 序写入必带 `SWP_NOOWNERZORDER`**：缺了它，移动子窗口会联动重排其 owner 链——实测 VS Code 集成终端的隐藏 `PseudoConsoleWindow`（owner=code）每个周期都被系统拖回"宿主正下方"槽位，与 250ms 自愈**永久互搏**：FixZOrder 每 tick 判定 needR=True → RAISE 两次 ok=True → 250ms 后又被拖回 → z 每 tick 翻转 = DWM 重合成 = **中线闪烁**（2026-11 日志实锤：31 分钟 770 次写入全是循环、校验目标态一次都没出现）。修复后 RAISE 只在真实事件出现（点击子窗口/激活/可见插队）
- **FixZOrder 校验必须跳过隐藏/cloaked 窗口**（与 `IsCoveredAtCursor` 同口径）：不可见插队者不渲染、不参与命中，为它翻转子窗口纯属浪费且每次写入都是一次重合成。不变量 = "宿主与子窗口之间无**可见**插队者"，不是"精确相邻"——隐藏杂窗（conhost/IME 辅助窗，本机开发时自己的工具调用就会产生）夹在中间是合法稳态
- **子窗口激活联动升顶**：`EVENT_SYSTEM_FOREGROUND`（DragAttach 第二钩子）→ 宿主 topmost-toggle 两步落普通带顶端（全程 `NOACTIVATE` 保焦点——`SetForegroundWindow(宿主)` 会打断子窗口输入；`HWND_TOP` 静默无效故不可用）→ `RaiseChildrenBelow` 粘回。语义 = 普通窗口"点哪整窗到前"，焦点留在被点的子窗口。**ALT+SetForegroundWindow 强制改前台不产生该事件**（合成测试无法走这条捷径，fg 真实变化但钩子收不到）；回归：`tools\tests\child_fg_raise_test.py`（点击区净空校验必须用 `GA_ROOT` 比对——Win11 notepad/mspaint 是多 HWND 应用，WindowFromPoint 命中的是内部控件如 RichEditD2DPT；点击区被前台抢占类程序（模拟器等）持有时 SKIP_FOREGROUND_HIJACK）
- 吸附子窗口设为 `WS_EX_TOOLWINDOW`（无任务栏/Alt+Tab）→ **最小化或独立最大化后无法手动恢复**，维护定时器（250ms）会自动拉回：子窗口没有"自己最大化"的概念
- **WindowChrome 的 resize 边命中测试不检查最大化状态**（WPF 源码 `_HitTestNca` 实证无该检查）：最大化时窗口顶边=屏幕顶边，顶条最上 8 DIP 被判成 HTTOP 缩放区、四边同理——鼠标按在屏幕顶上**拖不动**（拖顶条还原的 MouseDown 根本不触发；旧 maximize_drag_test 抓点 dy=14 DIP 恰在死区之下从未暴露）。修复 = 宿主 WndProc 拦 `WM_NCHITTEST`：最大化整窗回 `HTCLIENT`（最大化本就不可缩放 = Windows 标准；宿主 hook 在 WindowChromeWorker 之后挂接，实测能压过其命中结果）。回归：`tools\tests\max_top_drag_test.py`（含 NCHITTEST 逐行探针）
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
- **自动更新换装时序**（`src/Updater.cs`，逻辑全在那、宿主只做状态机）：发现新版本 → Available（⬇ + 状态栏通知），**启动自动检查绝不弹模态框**——线上版本比 CI 构建新时，回归套件里每个被测宿主启动 4s 后都被模态框禁用、UIA 点击全灭（CI 实测全红，job 42489188360）；弹确认框只走用户动作（点 ⬇ / 手动点 ↻ 检查）。确认框（`src/UpdateDialog.cs`，全主题化调色板快照 + Enter/Esc——系统 MessageBox 不随深浅色，同 ToolTip 换模板的考量；确认框内主题不会变，快照静态画刷即可，但 **Background 必须由 Style Setter 提供**——本地赋值优先级高于 Trigger，悬停会失效）→ 确认后下载（状态栏进度）→ 自动重启换装；取消留在 Available 可再点。换装 = `Closing` 处理器里**先** `OnClosingCleanup()`（子窗口还原 + 配置落盘，AttachedPids 随之清空、新实例不会误吸附）**再** rename 当前 exe 为 `.old` → move `.update` 到原路径 → `Process.Start`——运行中 exe **可改名不可覆写**（publish.py 同款事实）；任一步失败 `e.Cancel=true` 报因，窗口不关状态不丢。`.old` 会被退出中的旧进程占着删不掉：新实例启动清理 + 1.5s×4 重试自愈。版本比较只取**数字前缀**（InformationalVersion 可带 +hash/第4段，`Version.TryParse` 会拒收）；单文件下 `Assembly.Location` 为空串——取版本用 `AssemblyInformationalVersionAttribute`、取路径用 `Environment.ProcessPath`。测试钩子 `WM_UPDATE_API` 覆盖 releases/latest 地址（asset 下载地址取 JSON 自带 URL，不用第二处覆盖）；`releases/latest` 天然不含 prerelease/draft，404=无发布版本。更新按钮状态机只动 Content/ToolTip/IsEnabled + **UIA Name 跟随状态**（e2e 的状态探针）；**自动检查与手动点击的竞态必须守卫**（状态离开 Idle 就不覆盖——守卫丢失时两路检查各弹一个模态框叠栈，实测 UIA 拿句柄即失效）。回归 `tools\tests\update_e2e_test.py`

### 字体与资源（Font Awesome Free，SIL OFL；全部内嵌进程序集）
- 字体/图标在 `assets\`，以 `<Resource>` 内嵌（csproj），输出目录不落散资源文件
- **pack 字体必须经 XAML 声明**：`HostWindow.Resources` 里 `<FontFamily x:Key="FaSolid">pack://application:,,,/assets/<文件>#<完整家族名></FontFamily>`（FaRegular 同款）——这是唯一渲染正常的路径。**代码里 `new FontFamily(同样的 pack 字符串)` 能构造、GetResourceStream/GetFontFamilies 都正常，但 DWrite 渲染不解析（全部回退缺字）**——.NET 10 WPF 实测，别再试
- 无需运行时加载/校验代码：XAML 声明即渲染（字形直接写在按钮文本里，动态字形由 code-behind 切 Content）
- ico 内嵌后用 `BitmapDecoder.Create(资源流)` 解码取最大帧

### .NET 10 WPF 特有
- **Window 基类自带实验性 `ThemeMode` 属性**——自定义类名避开 `Theme`/`ThemeMode`（本项目用 `AppTheme`/`AppThemeMode`）

## 源码修改纪律

- **禁止用脚本正则批量改源文件**（历史教训：PowerShell 5.1 按系统 ANSI/GBK 读 UTF-8 文件，中文源文件曾因此整体乱码损毁）。源码修改只用 Edit 工具；确需跨文件批量修改时，只允许**显式 UTF-8 编码的精确串替换**（禁正则、逐文件核对该串唯一性），改完抽查
- **tools 脚本 = Python 3.14，一律经 uv 跑**（`uv run tools\<目录>\<脚本>.py`，首次自动建 .venv 并按 `pyproject.toml`/`uv.lock` 装依赖，`.python-version` 钉 3.14——comtypes 在 3.15 有 enum 行为变化告警勿升）：`tools\lib\wm.py` 公共库（ctypes Win32/截图/进程/config）；`wm_uia.py`：UIA 层用 **uiautomation 包**（comtypes 自动生成桩在 Py3.14 退化不可靠，勿回退）。脚本一律 `sys.path.insert(0, .../lib)` 后 `import wm`。中文注释可用（lib 已重配 stdout UTF-8）；诊断输出标记保持英文（NO_HOST / LEFT_HIT=...）。仅 `tools\archive\*.ps1` 是历史留档（ASCII-only，PS 5.1 时代产物），冻结不再维护勿新增——**新脚本一律 Python，不再写 PowerShell**
- 注释与 UI 文案用中文；异常直接抛出，不吞（唯一例外：配置文件损坏回退默认值、UIPI/DWM 属性调用失败按设计降级）

## 运行环境注意（Bash 工具 = Git Bash）

- `python` 指向 Windows Store stub（退出码 49）——Python 一律 `uv run`（`.venv` 由 uv 自管、`.python-version` 钉 3.14，不碰系统 python/py）
- 无 `%TEMP%` 等 CMD 展开，用 `$TEMP`/POSIX 路径；`tasklist`/`taskkill` 的过滤器斜杠要双写（`//FI`、`//PID`），否则被 Git Bash 当路径改写；`>nul` 是 Git Bash 里的普通文件重定向（会真建名为 nul 的文件），丢弃输出用 `>/dev/null`
- **复杂逻辑一律写 `tools\*.py` 脚本文件**再执行，不写内联长命令
- **锁屏会话（前台 = LockApp）时注入点击/键盘全部落在锁屏上，GDI 全屏截图报"句柄无效"**——远程交互验证会静默失败。此时 UIA `InvokePattern` 仍可用（进程内直调 Click，不走输入注入），可作为替代验证路径（见 `tools\visual\theme_menu_test.py`）
- 验证脚本截图后**必须还原层级**（`HWND_NOTOPMOST`），不得给用户正在运行的实例残留置顶
- Python 工具链实测坑（2026-11 转换期）：`SystemParametersInfoW(SPI_GETWORKAREA)` 本机 Win11 直接失败（err=0），主屏工作区用 `MonitorFromPoint(NEAREST)+GetMonitorInfo`；`SHGetKnownFolderPath` 第一参数是 **GUID 结构体指针**，传字符串地址不报错但返回未重定向的默认路径（本机桌面重定向 D:\Users）；psapi `GetModuleBaseNameW` 受限句柄查不到提权进程名，进程名一律 Toolhelp 快照；comtypes 1.4.17 对 UIAutomation typelib 生成的桩在 Python 3.14 上退化为 Incomplete（GetCurrentPattern 返回 NULL），UIA 层用 `uiautomation` 包；**打包应用（WindowsApps）进程 StartTime 不可靠**（预创建/挂起唤醒可早于宿主启动），"宿主拉起"判定用父进程链（`wm.launched_by`，stub→后代两层）；`shot.py` 的负坐标参数会被"未指定"哨兵吞掉，负坐标区域直接调 `wm.capture_screen`

## 验证流程

- **一键完整回归**：`uv run tools/run_all.py`（34 项自动测试按依赖顺序跑 + PASS/FAIL/SKIP 汇总表，`--only 名称` 跑子集）——**清理/回归会无差别关闭所有 WindowMerger/Notepad/mspaint——包括用户自己开着的实例**（Notepad 强杀，未保存内容丢失），跑之前先确认没有正在使用的窗口；子测试输出走**临时文件重定向**而非管道——测试超时 `taskkill /T` 树杀前，它拉起的孙进程（拖动靶窗/宿主）继承管道写句柄会让 communicate() 等 EOF 永久阻塞卡死整条套件（实测）；每个测试标题行 flush 保证重定向日志可看进度
- **CI（test.yml）已知限制**：runner 的 RDP 会话分辨率实测仅 **1024x720**（非 1920x1080）；covered_drag/drag_switch 两个注入拖动在 CI 确定性不生效（rect 纹丝不动、GetWindowRect 与可见位置漂移 ~27px、Ribbon 画图激活时功能区自变；四轮复现且本地同代码全 PASS）——两测试按屏宽 <1280 SKIP（`SKIP_CI_RDP_DRAG_NOT_ENGAGING`），拖动语义由本地覆盖；CI 桌面常驻一个浏览器窗口（占顶部），遮挡类断言注意；失败现场截图由 test.yml 上传为 `test-screenshots` artifact
- **CI 加固（2026-11）**：release.yml 复用 test.yml 当**发版门禁**（test.yml 加 `workflow_call`，release job `needs: test`）——发版前先跑同款构建+全量回归，测试不过不发版；run_all 把 35 项表格写进 `$GITHUB_STEP_SUMMARY`（Actions 运行页直读，不用拉原始日志——logs API 要管理员权限，实测折腾）+ 失败项发 `::error` 注解顶到页面头部；`WM_UPDATE_OFF=1`（test.yml job env + run_all setdefault，子进程继承）让被测宿主**不启动自动检查**——测试环境与真实 GitHub API 彻底断网（匿名限流看脸、线上版本 vs CI 构建版本的版本差会改被测行为=模态框事故根因）；手动点 ↻ 检查与 update_e2e 的 WM_UPDATE_API 本地假服务均不受影响
- **拖动类测试固定布局约定**（2026-11 实测）：布局单一来源 `wm.test_layout()`（按主屏工作区自适应物理像素矩形，`WM_TEST_LAYOUT=ci` 可在任何屏强制 CI 布局复现；4K 分支 = 工作区宽 ≥2560；**窄屏布局按经典版 mspaint 最小宽 514 设计，商店版最小 704x500 装不进 472px 格**——实测右格 deviation 420）；矮屏（高<1710，如 2560x1440 被远程工具降分辨率）下 4K 布局靶窗钉位 y=1090+620 探出屏缘，由各测试自行钳位：covered_drag 靶窗重钉宿主正下方并钳高（标题栏保持在宿主矩形外）、cursor_drop 的 mspaint 上移钳进屏内（与宿主重叠无碍——抓取走 ALT 置前台）；钉到主屏固定矩形（主屏坐标=物理像素，无跨 DPI 换算地雷——钉到 100% 左屏时 WPF 宿主会收 WM_DPICHANGED 自缩放，坐标全歪）；**跨 DPI 钉位（如 150% 左屏）必须两步走**：先移动收敛 DPI 再设尺寸，移动+尺寸一步到位会被改写（max_top_drag_test 实测 900x600 落成 400x450）——同 OnSourceInitialized 规则；窗口尺寸一律按**钉位后回读值**推导（PMv2 窗口被系统按 DPI 缩放，写死值不可信）；拖动抓点 = `wm.title_grab_point()`（WM_NCHITTEST 自窗口顶探第一个真实 HTCAPTION——几何推算无通用解：商店画图 rect 顶部 ~8px 是缩放热区会抓成 resize、Ribbon 画图标题条矮会抓进功能区；**HTCAPTION==2，10 是 HTLEFT** 写错常量全线抓到缩放区；SendMessage 必须 SendMessageTimeoutW(SMTO_ABORTIFHUNG) 防挂起窗口卡死套件）；注入拖动本身可靠，先前失败全是坐标假设过期；covered_drag/drag_switch 拖动靶 = 自写 tkinter 靶窗 `tools/targets/drag_target.py`（用户提议：零 Ribbon/零 PMv2、标题几何已知；mspaint 靶已弃用——notepad 自我缩放+最小尺寸钳制不可靠，商店画图抓点/热区随版本漂移）；**裸 WindowFromPoint 抓点检查要求靶窗标题栏在宿主矩形外**（抓进宿主空格会命中宿主 → SKIP_COVERED_GRAB）；cursor_drop 的 CASE_B 松手光标 y 直接构造为宿主上沿外 10px、窗口中心 y 随之落进左格（不依赖靶窗半高——半高不足时 target_cy+抓点dy-half_h 公式光标落进宿主内构造不成立，本机 Paint 11.2605 实测）
- 全流程回归：`uv run tools/tests\run_test_flow.py`（清理 → 开测试窗 → CLI 吸附 → 命中/矩形偏差 → 还原置顶状态）；选窗吸附 `tools\tests\picker_attach_test.py`、交换 `tools\tests\swap_sides_test.py`、几何持久化四场景 `tools\tests\geometry_persistence_test.py`、子窗口激活联动/z 自愈收敛/隐藏杂窗豁免 `tools\tests\child_fg_raise_test.py`（宿主停左侧屏 test 停放点；前台被抢占类程序持有时自动 SKIP）
- 跨 DPI 缝隙回归（4K+100% 双屏）：`uv run tools/tests\cross_dpi_seam_test.py`（96DPI mspaint 吸附进 150% 宿主，断言子窗口可见缘 ExtFrameBounds 与格子矩形四边 ≤1px；左侧显示器不在/非 100% 时 SKIP）
- 快捷方式生成回归：`uv run tools/tests\shortcut_create_test.py`（mspaint 单侧 + UIA 点按钮校验 .lnk 含 --left/--left-exe 完整路径；**不起 notepad——用户要求测试窗一律 mspaint、窗口由其人工选择**，mspaint 被占用时 SKIP 不强杀）
- 拉起吸附回归：`uv run tools/tests\launch_attach_test.py`（关闭 mspaint → 宿主带 `--left 名字 --left-exe 完整路径` 启动 → 断言宿主自己拉起 mspaint 且吸附成功；打包应用真实路径现场用 QueryFullProcessImageNameW 解析、不硬编码版本号路径）
- 自动更新 e2e：`uv run tools/tests\update_e2e_test.py`（本地 ThreadingHTTPServer 假 releases/latest + zip asset，`WM_UPDATE_API` 钩子指过去；UIA 按 AutomationId=UpdateButton 定位、UIA Name=状态文案当状态探针，弹窗确认流：检查（4s 自动检查抢跑与手动点击幂等，别硬编码时序假设）→ 确认框 UpdateConfirm 点击 → 下载（断言服务端收到 zip 请求）→ 重启安装（断言旧 PID 退出/新 PID 从原路径跑/`.old` 残留最终清掉）；**owned 弹窗在宿主 UIA 子树里也能走到**、`wm.wait_until` 只回布尔——要拿句柄自己轮询（实测两坑）；InvokePattern 锁屏可用、与遮挡无关）
- 单项工具（`tools\utils\`）：`rect/hit/shot/drag/win_cmd/atomic.py`（atomic = 置顶+截图+自动还原置顶，用于排查遮挡问题）
- 拖动类交互（最大化拖动还原/遮挡格拒收等）用交互式脚本人工验证：`tools\manual\manual_drag_test.py`（环境准备 + 每 150ms 采样打印时间线）、`tools\manual\covered_drag_test.py`（置顶遮罩盖右格，两步人工拖拽出判定）——注入式自动拖动受前台锁/覆盖窗干扰不可靠（实测反复 FAIL_COVERED），不要走回头路
- 主题/悬停类视觉验证（5 个带像素断言已入 run_all，调色板期望值在 `lib/wm.py` PALETTES）：`tools\visual\tooltip_shot.py`（悬停截 Tooltip 弹层 + 像素采样对调色板；**Tooltip 是独立弹窗，必须 CopyFromScreen 全屏截屏，PrintWindow 只能截宿主自己**；主题按钮定位用 UIA 取真实矩形——150% 下按 100% 偏移写死会落到最小化按钮上，实测）、`tools\utils\zoom_png.py`（PNG 区域放大，检字形/像素）、`tools\visual\theme_menu_shot.py`（真实点击截展开的主题菜单）；像素断言坑：WPF 自定义 Header 的 MenuItem UIA Name 为空（只能按索引 Invoke）；按钮中心正压字形，悬停采样取按钮顶部无字形区，且采样点/按钮中心不要写死 150% 校准值——100% 顶条（42px）下会压到字形或落到相邻按钮，一律 `get_dpi_for_window` 换算（hover_visual_test 实测）；任务栏按钮 UIA 名 = shell 应用识别名（**桌面快捷方式显示名优先于窗口标题**），按名找按钮搜"窗口合并"前缀而非 "WindowMerger"（icon_verify 实测）；探针（WindowFromPoint/截图）与光标悬停是两回事，snap 里动光标会让所有状态变悬停色；notepad 深色编辑器底色 ≈ ThemeBar（32,32,32），"透出子窗口"不能靠像素比对，断言吸附本身
- CLI 吸附验证的顺序：**先启动目标窗口，再带参启动宿主**（吸附发生在宿主 Loaded 时，目标必须已存在）。参数**纯数字 = PID、否则 = 进程名**；PID 三级回退：精确 PID → 后代进程树（Win11 打包应用经别名 stub 启动，`Start-Process -PassThru` 返回的 stub 没有窗口，真实窗口属于其后代进程，Toolhelp 快照走树匹配）→ 同名进程（stub 已退出的交接场景兜底）
- Win11 记事本是单实例多标签：同名目标会去重只吸一个，属预期
- 悬停任务栏弹窗的远程截图时机不稳定，最终视觉验收交给用户

## 已知边界（不要试图"修复"）

- **永远不要把子窗口的截图绘制进宿主窗口**（用户明确的永久规则，违反 = 预览假修复 + 点击被宿主拦截）
- **不做自定义缩略图/预览接管（iconic 位图方案已于 2026-11 移除）**：DWM 对 `FORCE_ICONIC` 窗口的缩略图请求尺寸恒为 200x109（不随 Alt-Tab 瓦片大小变化）、超尺寸位图 `E_INVALIDARG` 拒收、显示不放大——吸附态 Alt-Tab 瓦片无法铺满，无 API 可突破；而取消 FORCE 后宿主实时渲染只有顶条+透明格子（空面板），信息量更差。当前行为：任务栏/Alt+Tab 显示宿主实时画面（顶条 + 深色空格子），属已知取舍
- Alt+Tab/任务栏只显示宿主一项（子窗口 tool window 是吸附架构的一部分）
- 最大化时外边框隐藏（`CurBorderW`=0）、子窗口铺满格子，属设计
- 分隔条拖到极端比例时，右格可能窄于目标应用的最小宽度（如 mspaint ≈704px）——OS 钳制缩放，子窗口会探出宿主右缘约数十像素，非 bug
