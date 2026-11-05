# AGENTS.md — WindowMerger 项目约定

把任意两个独立窗口合并进同一个带边框宿主窗口（透明格子 + 子窗口吸附，**不用 SetParent**）。
技术栈：C# WPF，`net10.0-windows`，单项目（`WindowMerger.csproj`，入口 `src/App.xaml`，无 XAML 窗口——UI 全部代码构建）。

## 构建 / 运行 / 提交

```cmd
dotnet build -c Release        :: 必须做到 0 警告 0 错误
bin\Release\net10.0-windows\WindowMerger.exe [左进程名 右进程名]
bin\Release\net10.0-windows\WindowMerger.exe --left Code --right ZCode
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
- 吸附子窗口设为 `WS_EX_TOOLWINDOW`（无任务栏/Alt+Tab）→ **最小化或独立最大化后无法手动恢复**，维护定时器（250ms）会自动拉回：子窗口没有"自己最大化"的概念
- Win11 DWM 自动圆角是格子四角"圆角缝"的根源：吸附时设 `DWMWA_WINDOW_CORNER_PREFERENCE=DONOTROUND`，释放还原 `DEFAULT`
- 带框窗口有 ~7px 隐形边（`GetWindowRect` > 可见窗口）：吸附矩形按 `DWMWA_EXTENDED_FRAME_BOUNDS` 实测外扩，可见内容才与格子齐平
- UIPI：管理员权限窗口（如任务管理器）**无法**被普通权限程序吸附，`SetWindowPos` 静默失败——失败时必须状态回滚 + 状态栏报因
- 分隔条/格子几何一律用窗口 `ActualWidth` 直算，**不要读 `_content.ActualWidth`**（StateChanged 早于尺寸回缩完成，旧值会把分隔条顶偏）

### 字体（Font Awesome Free，SIL OFL）
- 字体用 `Content + CopyToOutputDirectory` 随 exe 分发，**文件路径**加载——本应用内 pack:// 资源流静默失败（`GetResourceStream` 返回 null）
- `GlyphTypeface` 不支持 pack:// URI；`FontFamily` 解析要用完整名 `Font Awesome 6 Free Solid` / `Font Awesome 6 Free Regular`（name 表 ID-1 名反而解析不到）
- 加载后必须字形自验证（`TryGetGlyphTypeface` + 探针码位存在）才算成功，失败回退 Unicode 字形

### .NET 10 WPF 特有
- **Window 基类自带实验性 `ThemeMode` 属性**——自定义类名避开 `Theme`/`ThemeMode`（本项目用 `AppTheme`/`AppThemeMode`）

## 源码修改纪律

- **禁止用 PowerShell 正则批量改源文件**：PS 5.1 按系统 ANSI（GBK）读 UTF-8 文件，中文源文件会整文件乱码损毁（本次 HostWindow.cs 曾因此整体重写）。源码修改只用 Edit 工具
- 写 `tools\*.ps1` 脚本时：**内容 ASCII-only**（UTF-8 无 BOM 被 PS 5.1 当 ANSI 读，中文字符串会破坏解析）；诊断输出用英文
- 注释与 UI 文案用中文；异常直接抛出，不吞（唯一例外：配置文件损坏回退默认值、UIPI/DWM 属性调用失败按设计降级）

## 运行环境注意（Bash 工具 = CMD）

- 无 POSIX 命令（`ls`/`grep`/`timeout` 均不可用）；延时用 `ping -n N 127.0.0.1 >nul`
- PowerShell 内联单行命令经 CMD 双层转义极易损坏（`$null` 转义、嵌套表达式不展开、中文参数变乱码）——**复杂逻辑一律写 `tools\*.ps1` 脚本文件**再执行，参数传数字/ASCII
- 验证脚本截图后**必须还原层级**（`HWND_NOTOPMOST`），不得给用户正在运行的实例残留置顶

## 验证流程

- 全流程回归：`powershell -NoProfile -ExecutionPolicy Bypass -File tools\RunTestFlow.ps1`（清理 → 开测试窗 → CLI 启动吸附 → 命中/矩形偏差 → 合成预览请求 → 悬停 → 读日志）
- 单项工具：`Rect/Hit/Shot/Drag/WinCmd/Atomic.ps1`（Atomic = 置顶+截图+自动还原置顶，用于排查遮挡问题）
- CLI 吸附验证的顺序：**先启动目标窗口，再带参启动宿主**（吸附发生在宿主 Loaded 时，目标必须已存在）
- Win11 记事本是单实例多标签：同名目标会去重只吸一个，属预期
- 悬停任务栏弹窗的远程截图时机不稳定，最终视觉验收交给用户

## 已知边界（不要试图"修复"）

- **永远不要把子窗口的截图绘制进宿主窗口**（用户明确的永久规则，违反 = 预览假修复 + 点击被宿主拦截）。任务栏/Alt+Tab 预览的正确实现是 iconic 位图应答：`DWMWA_FORCE_ICONIC_REPRESENTATION` + `DWMWA_HAS_ICONIC_BITMAP` **成对**设置（缺 HAS 时 DWM 悬停不发请求），悬停/Alt+Tab 时 DWM 发 `WM_DWMSENDICONIC*` 消息，用 PrintWindow 现场抓子窗口画面合成后经 `DwmSetIconicThumbnail/LivePreviewBitmap` 应答（见 HostWindow `UpdateIconicAttributes`/`CreateCompositeHBitmap`）；内容变化时调 `DwmInvalidateIconicBitmaps` 刷新
- 任务栏/Alt+Tab 预览显示的是应答时抓取的快照，非逐帧直播
- Alt+Tab/任务栏只显示宿主一项（子窗口 tool window 是吸附架构的一部分）
- 最大化时外边框隐藏（`CurBorderW`=0）、子窗口铺满格子，属设计
