# WindowMerger

把 VSCode / ZCode 等任意两个独立窗口合并进同一个带边框的宿主窗口——不用 `SetParent`，不注入、不 hook 目标窗口的消息循环，只做位置/尺寸/层级的持续对齐。

## 功能

- **透明格子 + 可见边框**：宿主窗口由 2px 边框、28px 顶条（拖动/双击最大化）、左右两个透明格子、中间 8px 分隔条组成；格子透明，空格直接看到桌面，吸附后透出子窗口
- **拖入吸附**：把任意窗口拖到宿主格子上，目标格高亮，松手吸附；拖到另一侧即换侧；替换时原窗口自动回到吸附前位置
- **顶条功能按钮**：选择左窗/右窗（候选列表 + 过滤）、交换左右、全部释放、─ □ ✕ 一字排开，悬停显示 tooltip；全部功能一个顶条搞定，无右键菜单
- **分隔条**：拖动实时调整左右比例（20%~80%），双击复位 50/50
- **窗口控制**：最大化只放大格子布局，不连坐子窗口的系统最大化；最小化/还原/切走切回全程联动，子窗口不会丢失
- **任务栏合成**：吸附的子窗口隐藏任务栏按钮与 Alt+Tab 项，宿主图标为两枚子窗口图标的叠加
- **配置持久化**：比例与宿主位置尺寸存于 `%APPDATA%\WindowMerger\config.json`

## 构建

需要 .NET 10 SDK（`net10.0-windows` + WPF）：

```cmd
dotnet build -c Release
```

 产物：`bin\Release\net10.0-windows\WindowMerger.exe`（运行时需要旁边的 `Resources\` 字体，构建自动复制）。

## 命令行

```cmd
WindowMerger.exe [--left 左进程名] [--right 右进程名]
WindowMerger.exe Code ZCode          :: 位置参数（左、右）
WindowMerger.exe --right mspaint     :: 只指定右格
```

- 启动即自动吸附对应进程的窗口；命名参数 `--left/-l`、`--right/-r` 可分别指定、任意顺序、只给一侧
- 进程名带不带 `.exe` 都可以，大小写不敏感
- 同名多窗口取当前面积最大的；最小化的会先还原再吸附
- 未找到的进程跳过并在状态栏提示；已吸附的窗口自动去重

## 主题

顶条 ◐ 按钮循环 **跟随系统 → 深色 → 浅色**（悬停 tooltip 显示当前状态），选择持久化到配置；
跟随系统模式下 Windows 切换深浅色时实时刷新（WM_SETTINGCHANGE）。

## 架构注记

- **外扩补偿**：Win11/DWM 给带框窗口留了约 7px 的隐形边，`GetWindowRect` 比可见窗口大。吸附时按 `DWMWA_EXTENDED_FRAME_BOUNDS` 实测外扩目标矩形，可见内容才能与格子齐平
- **z 序（关键）**：`SetWindowPos` 的 `hWndInsertAfter` 语义是"放到目标**下方**"。子窗口始终插在宿主**正下方**——宿主的不透明部分（顶条/边框/分隔条）盖住子窗口的隐形边，分隔条才可点击；透明格子处子窗口透出。250ms 维护定时器负责 z 序/布局自愈与样式补挂
- **P/Invoke**：`LibraryImport` 源生成器不会自动补 W 后缀，**自定义方法名也必须显式 `EntryPoint` 指向真实导出名**（`GetMonitorInfoW`/`GetWindowTextLengthW`/`DwmSetWindowAttributePointer` 均为此踩坑），且不支持 `StringBuilder` 参数（走经典 `DllImport`）；.NET Core 的 `GlyphTypeface` 不支持 pack:// URI
- **字体**：pack 资源流在本应用内静默解析失败（非标准 src 布局所致），故字体以 Content 随 exe 分发，按文件路径加载；可解析的家族名是完整名 `Font Awesome 6 Free Regular`。单字体（Regular 空心风格），f096/f24d/f2d1 直接覆盖；Regular 集不含 xmark，关闭按钮用 Segoe UI 的 ✕（WPF 字体回退）

## 字体许可

 `Resources\fa-solid-900.ttf` 与 `Resources\fa-regular-400.ttf` 来自 [Font Awesome Free](https://fontawesome.com/)（SIL OFL 1.1）。可随应用自由分发；若正式发布建议随附 OFL 许可文本。

## 目录

```
src/        源码（App.xaml 入口；HostWindow/DragAttach/PickerWindow/WindowLocator/Config/Icons/Native）
tools/      开发期验证脚本（截图/命中测试/窗口控制，PowerShell）
```
