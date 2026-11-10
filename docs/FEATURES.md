# WindowMerger 功能清单

把任意两个独立窗口"假合并"进同一个带边框的宿主窗口：**不用 `SetParent`、不注入消息**，只持续对齐位置/尺寸/z 序。本文按源码逐条核实，与 README 互补（README 偏使用，本文偏完整语义）。

## 核心机制

- 宿主 = 无边框透明 WPF 窗口（`WindowStyle=None + AllowsTransparency`），结构：2px 外框 + 28px 顶条 + 左右格子 + 6px 分隔条（`HostWindow.xaml` 为布局尺寸单一来源，code-behind 读入字段计算几何）
- 子窗口由 `AttachedChild` 封装：捕获吸附前矩形、设 `WS_EX_TOOLWINDOW` 隐藏任务栏/Alt+Tab 项、按 `DWMWA_EXTENDED_FRAME_BOUNDS` 现场实测外扩 DWM 隐形边后插到宿主正下方（宿主不透明部分盖住隐形边，透明格子透出子窗口、点击穿透交互）
- 250ms 维护定时器自愈：布局对账、z 序（"宿主正下方连续子窗口块"）、toolwindow 样式补挂、丢失子窗口检测

## 三种吸附途径

| 途径 | 实现 | 细节 |
|---|---|---|
| 拖入吸附 | `DragAttach`（全局 WinEvent hook） | 拖动中目标格亮蓝框，**以光标位置为准**（窗口中心在格内但光标不在不算），松手吸附；`IsCoveredAtCursor` 遍历 z 序判定遮挡（透明格子 alpha=0 在 OS 层点击穿透，不能 `WindowFromPoint` 直判） |
| 顶条选窗 | `PickerWindow` | 候选列表（标题/进程/PID/类名）+ 实时过滤 + 刷新；已吸附时按钮翻转成"释放该侧" |
| 命令行 | `App.ParseArgs` + `HostWindow.Attach.cs` | `--left/--right` 进程名\|PID（位置参数兜底）；PID 三级回退：精确 PID → 后代进程树（Win11 打包应用 stub）→ 同名进程；`--left-exe/--right-exe` 目标没开自动拉起（12s 轮询，宿主关闭中止） |

## 吸附行为规则

- 占用格拖入新窗默认拒绝并提示，**按住 Ctrl 拖入才替换**（旧窗回吸附前原位）；拖到另一侧 = 吸附态整体换侧（引用交换）
- 同名多窗口取面积最大的；最小化的先还原再吸附；已吸附窗口自动去重
- 管理员权限窗口无法吸附（UIPI 拦截 `SetWindowPos`）：状态回滚 + 状态栏报因
- **吸附成功立即 SaveConfig 落盘**（宿主被强杀时孤儿清理才有 HWND 可循）
- 启动时按上次配置的 HWND 精确清理孤儿（摘 TOOLWINDOW + 恢复任务栏收录 + 屏幕外 -32000 拉回）；PID 仅作句柄复用校验，**绝不按 PID 枚举进程全部窗口**（隐藏辅助窗口会被误显示成幽灵任务栏按钮）
- 候选/吸附排除：shell 窗口、无标题、owned、toolwindow、`WS_EX_TRANSPARENT` 穿透层、"另一个自己"（其他 WindowMerger 实例，含发布重命名变体）

## 顶条功能（全部功能一个顶条，无右键菜单）

- 更新组：无更新时隐藏；启动约 4s 自动检查一次 GitHub Release（主题菜单 `CheckUpdates` 开关，无手动检查入口），发现新版本 = 功能区最左现身「发现新版本 ⬇」+ 自动弹主题化确认框（一次性宣告）；确认或点 ⬇ 直接下载（状态栏进度）+ 优雅重启换装；取消后 ⬇ 保留，再点直接下载不重复询问；无更新/失败按钮保持隐藏
- `[←][→]` 选择左/右窗（空格）或释放该侧（已吸附，字形翻转）
- `[⇄]` 交换左右（引用交换，几何重排）
- `[⛓]` 全部释放（回吸附前矩形、恢复任务栏与圆角）
- `[📎]` 按当前组合生成桌面快捷方式：记录进程名 + exe 完整路径（提权/受保护进程降级仅名字），双击复现组合、目标没开自动拉起
- `[◐]` 主题下拉：跟随系统/深色/浅色直接选择，当前态带 ✓；Auto 模式经 `WM_SETTINGCHANGE` 实时跟随系统切换
- `[─][□][✕]` 最小化/最大化/关闭（Segoe Fluent Icons 原版标题栏字形，Win10 回退 MDL2）
- 状态栏：空格吸附提示 / 两侧窗口标题 / 3 秒临时通知（报因）
- 顶条拖动移动窗口、双击最大化；顶条悬停/分隔条悬停走 XAML Trigger 刷色

## 窗口状态联动

- **最大化只放大格子布局**（边框隐藏、子窗口随格子铺满），不触发子窗口系统最大化；`WM_GETMINMAXINFO` 钳制最大化到工作区
- 最大化状态拖顶条 = 按"光标在整窗占比"锚点还原并跟手移动（不用 `DragMove`，其模态循环与还原有竞态）
- 最小化：子窗口随动移出屏幕外（toolwindow 无任务栏按钮、最小化后无法手动还原）
- 宿主激活：拉子窗口回"宿主正下方"z 序（不用 `HWND_TOP`——Alt+Tab 切回后是静默无效调用）
- 子窗口被外部最小化/独立最大化：维护定时器拉回格子自愈（子窗口没有"自己最大化"的概念）
- 吸附时设 `DWMWA_WINDOW_CORNER_PREFERENCE=DONOTROUND` 直角化（消除 Win11 自动圆角的格子四角缝），释放还原 `DEFAULT`

## 任务栏合成

- Alt+Tab/任务栏只显示宿主一项（子窗口 toolwindow 是吸附架构的一部分）
- 宿主图标 = 两枚子窗口图标对角叠放（右=右上、左=左下）；单侧吸附时空位叠本程序图标占位——一眼看出还有一格空着
- 图标画布随 DPI（`GetSystemMetrics(SM_CXICON)`，32px@100% ↔ 48px@150%）；`WM_GETICON` 返回的是子窗口自有句柄，绝不 `DestroyIcon`
- 应用图标损坏时退化到单源拉伸，不崩

## 主题

- 深/浅两套 7 色 palette（`Theme.cs`）；Auto 读注册表 `AppsUseLightTheme`
- 刷色 = 换窗口资源（7 个 `Theme*Brush` 键，元素一律 `DynamicResource` 引用自动传播）；悬停走 XAML `IsMouseOver` Trigger（对 DynamicResource 做局部赋值会销毁资源引用表达式，禁止事件刷色）

## 配置持久化（`%APPDATA%\WindowMerger\config.json`）

- 内容：比例、主题、已吸附 PID/HWND（孤儿清理用）、**窗口几何**（正常态矩形物理像素 = DIP × 关闭时所在屏 DPI，最大化/最小化关闭取 `RestoreBounds`）+ 是否最大化；旧字段反序列化自动忽略
- 启动恢复：目标屏 = 保存矩形中心最近可见显示器；尺寸/位置钳制到其工作区（断屏/改分辨率/垃圾配置含 L≥R 都不出屏外幽灵窗，无有效几何默认 1280×800 居中）
- 跨 DPI 落位两步走：`OnSourceInitialized` 先 `SetWindowPos` 移动（触发 `WM_DPICHANGED` 收敛目标屏缩放）再设尺寸（WPF 跨 DPI 保 DIP 不保物理，一步到位会被改写）
- 配置损坏回退默认值，不阻断启动

## 发布链路

- 本地：`tools\publish\` 打包脚本（WM_CLOSE 优雅关运行实例 → 复用 `Properties\PublishProfiles\FolderProfile.pubxml`（打包设置唯一来源）→ `publish\WindowMerger-<版本>-win-x64.exe`，框架依赖单文件，目标机器需 .NET 10 Desktop Runtime x64）
- GitHub Actions 两条路：推 `v*` tag 发 Release / dispatch 手动触发（可自动建 tag、可勾 prerelease）；main push 只跑 `test.yml` 全量回归，不发版

## 已知边界（设计取舍，不是 bug）

- 永远不把子窗口截图绘制进宿主窗口（预览假修复 + 点击被宿主拦截）
- 吸附态 Alt+Tab 瓦片显示宿主实时画面（顶条 + 深色空格子）——iconic 位图方案已验证不可行（DWM 请求尺寸恒 200×109、超尺寸 `E_INVALIDARG`）
- 分隔条拖到极端比例时右格可能窄于目标应用最小宽度，OS 钳制缩放、子窗口探出宿主右缘数十像素
