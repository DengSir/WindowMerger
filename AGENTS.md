# AGENTS.md — WindowMerger 项目约定

把任意两个独立窗口合并进同一个带边框宿主窗口（透明格子 + 子窗口吸附，**不用 SetParent**）。
技术栈：C# WPF，`net10.0-windows`，单项目（`WindowMerger.csproj`，入口 `src/App.xaml`，宿主视觉树在 `src/HostWindow.xaml`——`x:Name` 生成字段供 code-behind 引用，动态逻辑全在 `HostWindow.xaml.cs`；构造顺序 = InitializeComponent → WireUi（事件/按钮填充）→ ApplyTheme（按配置主题重刷，XAML 只带深色初值）→ 配置尺寸覆盖）。

## 构建 / 运行 / 提交

```cmd
dotnet build -c Release        :: 必须做到 0 警告 0 错误
bin\Release\net10.0-windows\WindowMerger.exe [左进程名|左PID 右进程名|右PID]
bin\Release\net10.0-windows\WindowMerger.exe --left Code --right ZCode
bin\Release\net10.0-windows\WindowMerger.exe --left 12345 --right mspaint
```

- **重建前必须先关闭运行中的实例**（exe 被运行实例锁定会构建失败）。优雅关闭 = PostMessage `WM_CLOSE (0x0010)`，走正常退出流程（保存配置 + 释放子窗口回原位）；`taskkill /F` 会跳过这些清理，仅在卡死时用
- 功能迭代单独 commit；`bin/`、`obj/`、`.zcode/` 已在 .gitignore，勿入库

## 本仓库踩过的真坑（违反必炸，全部实测）

### P/Invoke（LibraryImport 源生成器）
- **不会自动补 W 后缀**：自定义方法名必须显式 `EntryPoint` 指向真实导出名。已为此崩过三次：`GetMonitorInfoW`、`GetWindowTextLengthW`、`DwmSetWindowAttributePointer→DwmSetWindowAttribute`。新增 P/Invoke 时先确认真实导出名
- **不支持 `StringBuilder` 参数**：字符串出入参走经典 `DllImport`（CharSet.Unicode）
- `dwmapi` 属性 `DWMWA_FORCE_ICONIC_REPRESENTATION` **只写不可读**（Get 返回 E_INVALIDARG）——不要用读回验证它

### WPF / Win32 语义
- `SetWindowPos` 的 `hWndInsertAfter` = "放到目标窗口**下方**"。子窗口吸附 z 序 = 子窗口永远插在宿主**正下方**（宿主不透明部分盖住子窗口隐形边，分隔条才可点击；透明格子透出子窗口）
- **拉起子窗口 z 序不要用 `HWND_TOP`**：Alt+Tab 切回宿主后它是**静默无效调用**（返回 true 但 z 序不变，子窗口被切走前的窗口一直压住，实测必现）；z 序修复一律相对插入 `hWndInsertAfter = 宿主`，自愈校验用"宿主正下方连续子窗口块"（见 `FixZOrder`）。复现/回归：`tools\AltTabZRepro.ps1`
- 吸附子窗口设为 `WS_EX_TOOLWINDOW`（无任务栏/Alt+Tab）→ **最小化或独立最大化后无法手动恢复**，维护定时器（250ms）会自动拉回：子窗口没有"自己最大化"的概念
- Win11 DWM 自动圆角是格子四角"圆角缝"的根源：吸附时设 `DWMWA_WINDOW_CORNER_PREFERENCE=DONOTROUND`，释放还原 `DEFAULT`
- 带框窗口有 ~7px 隐形边（`GetWindowRect` > 可见窗口）：吸附矩形按 `DWMWA_EXTENDED_FRAME_BOUNDS` 实测外扩，可见内容才与格子齐平
- UIPI：管理员权限窗口（如任务管理器）**无法**被普通权限程序吸附，`SetWindowPos` 静默失败——失败时必须状态回滚 + 状态栏报因
- 分隔条/格子几何一律用窗口 `ActualWidth` 直算，**不要读 `_content.ActualWidth`**（StateChanged 早于尺寸回缩完成，旧值会把分隔条顶偏）
- **强杀宿主 = 孤儿**：吸附子窗口残留 `WS_EX_TOOLWINDOW`（任务栏消失，宿主最小化期间被强杀还会停在屏幕外 -32000）。孤儿清理必须**按配置记录的 HWND 精确匹配**（PID 仅作句柄复用校验），**绝不能按 PID 枚举该进程全部窗口**——进程的隐藏辅助窗口（`CiceroUIWndFrame` 等，实测 opera/Listary/RepositoryTree 都带 TOOLWINDOW）会被误显示成"点不出来的任务栏幽灵按钮"。吸附成功立即 SaveConfig 落盘（强杀时才有记录可循）。救援 `tools\OrphanRescue.ps1`，回归 `tools\OrphanE2ETest.ps1`

### 字体与资源（Font Awesome Free，SIL OFL；全部内嵌进程序集）
- 字体/图标在 `assets\`，以 `<Resource>` 内嵌（csproj），输出目录不落散资源文件
- **pack 字体必须经 XAML 声明**：`App.xaml` 里 `<FontFamily x:Key="FaSolid">pack://application:,,,/assets/<文件>#<完整家族名></FontFamily>`，代码用 `TryFindResource` 取用——这是唯一渲染正常的路径。**代码里 `new FontFamily(同样的 pack 字符串)` 能构造、GetResourceStream/GetFontFamilies 都正常，但 DWrite 渲染不解析（全部回退缺字）**——.NET 10 WPF 实测，别再试
- 校验用**渲染宽度对比**（探针码位 vs 确定缺失的私用区码位 U+F8FF，宽度不同 = 字形真实）——`GlyphTypeface`/`TryGetGlyphTypeface`/`GetTypefaces` 对 pack 字体均不可用
- `Fonts.GetFontFamilies` 对同目录 pack 字体有家族名串扰（regular 文件会列出 solid 的家族名）——不能用它做家族名精确校验
- `FontFamily` 解析要用完整名 `Font Awesome 6 Free Solid` / `Font Awesome 6 Free Regular`（name 表 ID-1 名反而解析不到）
- 校验失败结果要一并缓存（`??=` 模式不会缓存 null，会每 250ms 重试解析）
- ico 内嵌后用 `BitmapDecoder.Create(资源流)` 解码取最大帧

### .NET 10 WPF 特有
- **Window 基类自带实验性 `ThemeMode` 属性**——自定义类名避开 `Theme`/`ThemeMode`（本项目用 `AppTheme`/`AppThemeMode`）

## 源码修改纪律

- **禁止用 PowerShell 正则批量改源文件**：PS 5.1 按系统 ANSI（GBK）读 UTF-8 文件，中文源文件会整文件乱码损毁（本次 HostWindow.cs 曾因此整体重写）。源码修改只用 Edit 工具
- 写 `tools\*.ps1` 脚本时：**内容 ASCII-only**（UTF-8 无 BOM 被 PS 5.1 当 ANSI 读，中文字符串会破坏解析）；诊断输出用英文
- 注释与 UI 文案用中文；异常直接抛出，不吞（唯一例外：配置文件损坏回退默认值、UIPI/DWM 属性调用失败按设计降级）

## 运行环境注意（Bash 工具 = CMD）

- 无 POSIX 命令（`ls`/`grep`/`timeout` 均不可用）；延时用 `ping -n N 127.0.0.1 >nul`
- PowerShell 内联单行命令经 CMD 双层转义极易损坏（`$null` 转义、嵌套表达式不展开、中文参数变乱码）——**复杂逻辑一律写 `tools\*.ps1` 脚本文件**再执行，参数传数字/ASCII
- **锁屏会话（前台 = LockApp）时注入点击/键盘全部落在锁屏上，GDI 全屏截图报"句柄无效"**——远程交互验证会静默失败。此时 UIA `InvokePattern` 仍可用（进程内直调 Click，不走输入注入），可作为替代验证路径（见 `tools\ThemeMenuTest.ps1`）
- 验证脚本截图后**必须还原层级**（`HWND_NOTOPMOST`），不得给用户正在运行的实例残留置顶

## 验证流程

- 全流程回归：`powershell -NoProfile -ExecutionPolicy Bypass -File tools\RunTestFlow.ps1`（清理 → 开测试窗 → CLI 启动吸附 → 命中/矩形偏差 → 还原置顶状态）
- 单项工具：`Rect/Hit/Shot/Drag/WinCmd/Atomic.ps1`（Atomic = 置顶+截图+自动还原置顶，用于排查遮挡问题）
- 拖动类交互（最大化拖动还原等）用 `ManualDragTest.ps1` 交互式验证：脚本只准备环境 + 每 150ms 采样窗口状态，**人工实际拖动**、回车后打印时间线——注入式自动拖动受前台锁/覆盖窗干扰不可靠（实测反复 FAIL_COVERED），不要走回头路
- CLI 吸附验证的顺序：**先启动目标窗口，再带参启动宿主**（吸附发生在宿主 Loaded 时，目标必须已存在）。参数**纯数字 = PID、否则 = 进程名**；PID 三级回退：精确 PID → 后代进程树（Win11 打包应用经别名 stub 启动，`Start-Process -PassThru` 返回的 stub 没有窗口，真实窗口属于其后代进程，Toolhelp 快照走树匹配）→ 同名进程（stub 已退出的交接场景兜底）
- Win11 记事本是单实例多标签：同名目标会去重只吸一个，属预期
- 悬停任务栏弹窗的远程截图时机不稳定，最终视觉验收交给用户

## 已知边界（不要试图"修复"）

- **永远不要把子窗口的截图绘制进宿主窗口**（用户明确的永久规则，违反 = 预览假修复 + 点击被宿主拦截）
- **不做自定义缩略图/预览接管（iconic 位图方案已于 2026-11 移除）**：DWM 对 `FORCE_ICONIC` 窗口的缩略图请求尺寸恒为 200x109（不随 Alt-Tab 瓦片大小变化）、超尺寸位图 `E_INVALIDARG` 拒收、显示不放大——吸附态 Alt-Tab 瓦片无法铺满，无 API 可突破；而取消 FORCE 后宿主实时渲染只有顶条+透明格子（空面板），信息量更差。当前行为：任务栏/Alt+Tab 显示宿主实时画面（顶条 + 深色空格子），属已知取舍
- Alt+Tab/任务栏只显示宿主一项（子窗口 tool window 是吸附架构的一部分）
- 最大化时外边框隐藏（`CurBorderW`=0）、子窗口铺满格子，属设计
- 分隔条拖到极端比例时，右格可能窄于目标应用的最小宽度（如 mspaint ≈704px）——OS 钳制缩放，子窗口会探出宿主右缘约数十像素，非 bug
