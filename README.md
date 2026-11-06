# WindowMerger

把 VSCode / ZCode 等任意两个独立窗口合并进同一个带边框的宿主窗口——不用 `SetParent`，不注入、不 hook 目标窗口的消息循环，只做位置/尺寸/层级的持续对齐。

## 功能

- **透明格子 + 可见边框**：宿主窗口由 2px 边框、28px 顶条（拖动/双击最大化）、左右两个格子、中间 6px 分隔条组成；空格显示填充与提示文案，吸附后恢复透明透出子窗口（点击穿透到子窗口交互）
- **拖入吸附**：把任意窗口拖到宿主格子上，目标格高亮，松手吸附；拖到另一侧即换侧；替换时原窗口自动回到吸附前位置
- **顶条功能按钮**：选择左窗/右窗（候选列表 + 过滤）、交换左右、全部释放、快捷方式（按当前吸附生成桌面 .lnk，记录进程名 + exe 完整路径，双击复现组合——目标应用没开也会自动拉起）、◐ 主题（下拉直接选择）、─ □ ✕ 一字排开，悬停显示 tooltip；全部功能一个顶条搞定，无右键菜单
- **分隔条**：拖动实时调整左右比例（20%~80%），双击复位 50/50
- **窗口控制**：最大化只放大格子布局，不连坐子窗口的系统最大化，最大化状态下拖动顶条可还原并跟手移动；最小化/还原/切走切回全程联动，子窗口不会丢失
- **任务栏合成**：吸附的子窗口隐藏任务栏按钮与 Alt+Tab 项，宿主图标为两枚子窗口图标的对角叠放（右=右上、左=左下）；只吸一侧时空位叠本程序图标占位
- **配置持久化**：比例、主题、窗口几何存于 `%APPDATA%\WindowMerger\config.json`。几何 = 正常态矩形（物理像素）+ 是否最大化，启动恢复位置/尺寸/最大化状态；恢复时校验钳制到最近可见显示器的工作区（显示器断开/分辨率变化/配置损坏都不会出现屏外幽灵窗），跨 DPI 不漂移

## 构建

需要 .NET 10 SDK（`net10.0-windows` + WPF）：

```cmd
dotnet build -c Release
```

产物：`bin\Release\net10.0-windows\WindowMerger.exe`（字体/图标已内嵌进程序集，输出目录无散落资源文件）。

## 发布

**本地打包**（框架依赖单文件 exe，win-x64）：

```cmd
py tools\publish\publish.py
py tools\publish\publish.py --version 1.2.3
```

- 打包参数复用 VS 发布配置 `Properties\PublishProfiles\FolderProfile.pubxml`（win-x64 / 框架依赖 / 单文件 / 输出 `publish\`）——在 VS 发布对话框里改设置，脚本与 CI 自动跟随
- 产物：`publish\WindowMerger-<版本>-win-x64.exe`，版本默认取自 csproj 的 `<Version>`
- 脚本先以 `WM_CLOSE` 优雅关闭运行中的实例（保存配置、子窗口回原位），再以 `TreatWarningsAsErrors` 发布（强制 0 警告 0 错误）
- 目标机器需安装 [.NET 10 Desktop Runtime (x64)](https://dotnet.microsoft.com/download/dotnet/10.0)

**GitHub 自动发布**：推 tag 即自动构建并发 Release：

```cmd
git tag v1.2.3
git push origin v1.2.3
```

`.github/workflows/release.yml` 在 `windows-latest` 上执行与本地相同的发布命令（同样引用 FolderProfile），把 `WindowMerger-<版本>-win-x64.exe` 附到 [Releases](https://github.com/DengSir/WindowMerger/releases)，Release 说明由提交记录自动生成，版本号（去掉 `v` 前缀）会作为程序集版本写入 exe。两条发版路径：

- **推 tag**（`git tag v0.1.0 && git push origin v0.1.0`）：从 tag 本身发 Release
- **Actions 页手动触发**（可在 main 上直接发，无需预推 tag）：填 `version`（如 `0.1.0`、`0.1.0-alpha.1`，`v` 前缀可省）即在该分支当前 HEAD 上自动创建 tag 并发 Release，可勾选 `prerelease` 标记预发布；`version` 留空则只构建上传工件、不发 Release

## 命令行

```cmd
WindowMerger.exe [--left 左进程名|PID] [--right 右进程名|PID] [--left-exe 左exe路径] [--right-exe 右exe路径]
WindowMerger.exe Code ZCode          :: 位置参数（左、右）
WindowMerger.exe --right mspaint     :: 只指定右格
WindowMerger.exe 12345 mspaint       :: 纯数字参数按 PID 匹配
WindowMerger.exe --left Code --left-exe "C:\...\Code.exe"  :: 附带完整路径
```

- 启动即自动吸附对应进程的窗口；命名参数 `--left/-l`、`--right/-r` 可分别指定、任意顺序、只给一侧
- 进程名带不带 `.exe` 都可以，大小写不敏感
- 纯数字参数按 PID 匹配，三级回退：精确 PID → 后代进程树（Win11 打包应用经 stub 启动，真实窗口属后代进程）→ 同名进程兜底
- `--left-exe`/`--right-exe` 记录目标 exe 完整路径（快捷方式自动生成）：名字/PID 匹配不到时先按镜像路径匹配已运行窗口，仍没有就**自动拉起**该 exe 并等窗口出现（最长 12 秒）后吸附——目标应用没开也能复现组合；单实例应用（如 Win11 记事本）与打包应用（stub→后代进程）天然覆盖；打包应用路径含版本号（WindowsApps 下），应用更新后路径会变——名字匹配照常生效，拉起会提示路径不存在（重新生成一次快捷方式即可）
- 同名多窗口取当前面积最大的；最小化的会先还原再吸附
- 未找到的进程跳过并在状态栏提示；已吸附的窗口自动去重

## 主题

顶条 ◐ 按钮弹出下拉菜单，**跟随系统 / 深色 / 浅色** 直接选择（悬停 tooltip 显示当前状态），选择持久化到配置；
跟随系统模式下 Windows 切换深浅色时实时刷新（WM_SETTINGCHANGE）。

## 架构注记

- **外扩补偿**：Win11/DWM 给带框窗口留了约 7px 的隐形边，`GetWindowRect` 比可见窗口大。吸附时按 `DWMWA_EXTENDED_FRAME_BOUNDS` 实测外扩目标矩形，可见内容才能与格子齐平
- **z 序（关键）**：`SetWindowPos` 的 `hWndInsertAfter` 语义是"放到目标**下方**"。子窗口永远插在宿主**正下方**（不能用 `HWND_TOP`——Alt+Tab 切回宿主后是静默无效调用）：宿主的不透明部分（边框/分隔条/顶条）盖住子窗口的隐形边，分隔条才可点击，透明格子则透出子窗口。宿主激活后立即+低优先级重拉子窗口，250ms 维护定时器按"宿主正下方连续子窗口块"精确遍历自愈 z 序、修布局与样式补挂
- **字体**：FA 双字体（Solid/Regular）以 `Resource` 内嵌进程序集（pack 字体经 XAML 声明）；可解析的家族名是完整名 `Font Awesome 6 Free Solid/Regular`；Regular 集不含 xmark，关闭按钮用 Segoe UI 的 ✕（WPF 字体回退）
- **P/Invoke**：`LibraryImport` 源生成器不会自动补 W 后缀，**自定义方法名也必须显式 `EntryPoint` 指向真实导出名**（`GetMonitorInfoW`/`GetWindowTextLengthW`/`DwmSetWindowAttributePointer` 均为此踩坑），且不支持 `StringBuilder` 参数（走经典 `DllImport`）；.NET Core 的 `GlyphTypeface` 不支持 pack:// URI

## 字体许可

 `assets\fa-solid-900.ttf` 与 `assets\fa-regular-400.ttf` 来自 [Font Awesome Free](https://fontawesome.com/)（SIL OFL 1.1）。可随应用自由分发；发布版请在 Release 说明中注明字体许可。

## 目录

```
src/        源码（App.xaml 入口；HostWindow.xaml + HostWindow.cs/Attach/Drag 三个 partial、
            AttachedChild 吸附态、DragAttach 拖入吸附、PickerWindow 选窗、WindowLocator 候选、
            Config 持久化、Theme 主题、Native Win32）
docs/       FEATURES.md 功能清单（按源码核实）
tools/      开发/验证/发布脚本（Python），按用途分目录（publish 打包 / tests 自动回归 /
            manual 人工验证 / visual 视觉验证 / utils 单项工具 / archive 历史留档），
            清单见 tools/README.md；lib/ 为公共库（ctypes Win32 + UIA）
```

**开发脚本依赖**：应用本身不需要 Python；跑 `tools/` 脚本需要 Python 3.14 + `py -m pip install pillow comtypes`（截图与 UI Automation）。
