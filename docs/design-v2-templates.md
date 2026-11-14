# v2 设计：宿主模板化（任意 snap 布局）

状态：设计稿（未实施）。v1（二格 snap 接管）已落地于 d3fc714，图标时序修复于 43fafd4。
本文是 docs/todo.md 各条目的唯一详细设计来源；实施时逐条对照，条目完成即在 todo.md 勾销。

## 1. 目标与范围

- 宿主从"写死两格"泛化为**模板驱动 N 格**：支持 Win11 snap 全谱（2 区对半/2:1/上下、3 区三等分/半+两叠、4 区田字/半+三叠、6 区三列双行等 shell 固定模板集）。
- 托盘热键从"只接恰好 2 窗"放开到"按检测到的模板整组接管"。
- **二格降级为模板特例**（1 条竖分隔、ratio 0.5 的 template），存量行为与测试不破坏。
- 不做（明确出界）：用户自定义任意模板编辑器；跨宿主拖拽子窗口搬家（同宿主格间交换保留）；v1 已知已接受代价（Snap 浮层、UIPI）维持。

## 2. 模板模型

### 2.1 数据结构（新文件 `src/PaneTemplate.cs`）

```csharp
// 递归二分树：矩形布局的表达力足够（Win11 全部模板都是矩形嵌套切分），
// 且每条内部分隔天然对应一根可拖动的 divider
internal sealed record PaneTemplate(string Id, TemplateNode Root)
internal abstract record TemplateNode
    // 叶子 = 一个格子；Split = 沿比例线切两半（Vertical=true 竖切）
    internal sealed record ZoneNode(int ZoneId) : TemplateNode
    internal sealed record SplitNode(bool Vertical, double Ratio, TemplateNode First, TemplateNode Second) : TemplateNode
```

- 内置模板目录（静态只读）：`binary-50`(v1 现状)、`binary-67`、`stack-v50`、`thirds-3`、`halves-2stack`、`quad`、`halves-3stack`、`grid-3x2`…按 Win11 shell 模板集 1:1 定义，Id 稳定可持久化。
- `TemplateNode.CollectZones()` → 有序 `List<Rect>`（DIP，占位布局计算）；`EnumerateSplits()` → 全部 `SplitNode`（每根分隔一条）。
- **ZoneId 分配规则**：先序遍历 0..n-1。持久化与检测都依赖该稳定性，定死不改。

### 2.2 宿主视觉树动态生成（改 `src/HostWindow.xaml` + `HostWindow.cs`）

- XAML 保留：`_outer` 边框、`_topBar`、状态栏——静态外壳不动（布局尺寸单一来源纪律不变）。
- `_content` 内部由 `ApplyTemplate()` 代码生成：`Grid` 嵌套实现 Split 树（每层 3 列/行：`*` | 分隔宽 | `*`），分隔条是 `Border`/`Thumb` 实例（样式复用现有 `DividerStyle`，悬停 Trigger + DynamicResource 不变）。
- 现有 `_dividerW` 读取逻辑（`WireUi` 从 XAML 列宽读）改为模板生成的分隔列统一取常量 `_dividerW`（值仍来自 XAML 资源，单一来源不破坏）。
- 空格占位提示（`UpdatePaneHints` 的 ThemeBar 填充+文案）逐 zone 生成；**吸附格必须回到透明**的既有规则逐 zone 保持。

## 3. 宿主书簿重构（改 `src/HostWindow.cs` / `HostWindow.Attach.cs` / `HostWindow.Drag.cs`）

### 3.1 Pane 抽象

```csharp
internal sealed class Pane   // 替代 _left/_right 引用对
{
    public int ZoneId;
    public AttachedChild? Child;   // null = 空格
    public Rect DeviceRect;        // 当帧格子矩形（物理 px，PlaceInPane 用）
}
private List<Pane> _panes;     // ZoneId 有序
private PaneTemplate _template;
```

- `ChildAt(side)` → `PaneAt(zoneId)`；`HwndOf`、`IsAttachedChild`、`UpdateStatus`（状态栏 `左:/右:` → 按 zone 序拼接）、`UpdateSideButtons`（v1 二格侧按钮在 N 格下：保留前两格语义 or 收纳进菜单——**决策：v2 顶条侧按钮只服务前两个 zone**，其余 zone 靠拖拽/接管，避免顶条按钮无限增长）。
- **TryAttach 泛化**：`AttachSide side` 参数 → `int zoneId`；分支逻辑（拖回原格/占用拒换/Ctrl 替换/换侧）逐条对应到 pane 语义；"换到另一侧"（`hwnd == otherHwnd`）在 N 格下 = `hwnd == 任一 pane.Child.Hwnd` → 引用搬家。
- **SwapSides**：保留为二格特例按钮（`_template == binary` 时才显示）；N 格无全局 swap 语义。
- **ReleaseAll / ReleaseSide / ReleaseHiddenSide / DetachStateOnly / CleanupOrphanedChildren**：遍历 `_panes`，逻辑不变。
- **Maintain/FixZOrder/EnsureChildDocked**：遍历 `_panes`；`FixZOrder` 的"宿主正下方连续子窗口块"不变量不变。

### 3.2 AttachedChild（预计零改动或近零）

`src/AttachedChild.cs` 全部 API 按 `PlaceInPane(rect)`/宿主句柄工作，与格子数解耦——v1 解耦的直接回报。唯一核查点：`EnsureDockedState` 的"连续两周期不可见→释放"上报目标是宿主（`ReleaseHiddenSide(side)` → `ReleaseHiddenSide(zoneId)`）。

### 3.3 几何公式（改 `HostWindow.Drag.cs`）

- `UpdatePaneWidths`/`ApplyLayout`/`PaneRectDevice`：单 ratio 公式 → 按 Split 树递归求各 zone 设备矩形（DIP×DPI 换算沿用现有模式；`ActualWidth` 直算纪律不变，禁读 `_content.ActualWidth`）。
- **分隔条拖动**：`DividerOnMouseDown/Move/Up`（`src/HostWindow.Drag.cs:99/113/124`）当前绑定单根分隔。重构：每根生成的分隔条实例带 `(SplitNode 引用, 父容器方向)`，拖动只改**该 SplitNode.Ratio**（clamp [0.15, 0.85] 每 split；田字十字是两条独立 split，各拖各的）。Ratio 集合持久化见 §5。
- `HitTestPaneAt`（Drag.cs:131）/`SetDragHighlight`/DragAttach 的 `HitTestSlot`（`src/DragAttach.cs:83`）：`AttachSide?` → `int?`（zoneId），命中=遍历 zone 设备矩形 Contains。
- 最大化 TopInset=0、顶条自动隐藏、`CurBorderW`：与格数正交，不动。

## 4. 检测器 v2（改 `src/SnapLayoutDetector.cs`）

- **拓扑重建替代模板穷举**：对一组贴合窗口，按共享边合并出"切分图"→ 递归二分拟合（每次找一条贯穿切线，二分成两子问题，直到每块恰含一个窗口）→ 直接产出 `PaneTemplate` + zone→hwnd 映射。拟合失败（存在无法用二分树表达的排布）→ 报因 `UNSUPPORTED_LAYOUT`。模板目录匹配只做**命名**（找 Id 最接近的内置模板），命中失败也可以用动态模板接管（split ratio 用实测值）。
- v1 的判据全部保留复用：EFB 口径、面积 ≥5%、并集≈工作区（8px 容差）、**贴合子集搜索**（`Classify` 2^N 枚举互不重叠且并集≈工作区的子集，2026-11-14 替代旧的"面积降序贪心去重叠"——贪心会把盖住 snap 组的漂浮大窗当成员、把真成员挤掉）、共享边分类。`SharesVerticalEdge/STACKED` 的"只认二窗"特判删除，由拓扑重建统一吸收。
- 输出结构升级：`SnapGroup` 增加 `Template PaneTemplate` 与 `List<(int ZoneId, IntPtr Hwnd)>`；`--detect-snap` JSON 相应扩展（保持 v1 字段兼容：2 窗时 `left/right/ratio` 继续输出）。
- 上下排列（v1 报 STACKED）在 v2 是合法模板（`stack-v50`），报因移除。

## 5. 配置与迁移（改 `src/Config.cs` / `HostWindow.cs SaveConfig`）

```jsonc
{
  "Template": "binary-50",           // 新；null/缺省 = 旧二格行为
  "Splits": { "id-path": 0.5, ... }, // 每 SplitNode 的 ratio（键=树路径，如 "0.1"）
  "AttachedHwnds": [...],            // 语义不变，长度=吸附数（可 >2）
  "AttachedPids": [...],
  // Ratio 字段保留只读兼容（旧配置迁移到 Template=binary-50 + Splits{"0": ratio}）
}
```

- 迁移规则：读到旧格式（有 `Ratio` 无 `Template`）→ 构造 `binary-50` + 单 split ratio=旧值，写回新格式。`config_edge_test` 增补场景。
- v1 的 `--profile` 隔离、孤儿记录（`AttachedHwnds` 已是 list 天然支持 N）、接管实例 `CheckUpdates=false` 全部沿用。

## 6. 托盘与 CLI 对接（改 `src/TrayController.cs` / `src/App.xaml.cs` / `src/HostWindow.Attach.cs`）

- 托盘 `Capture()`：`DetectAndPick` 拿到模板+映射后，spawn 参数从 `--left-hwnd/--right-hwnd` 升级为 `--template <id> --zones "0=hwnd1,1=hwnd2,..."`（二窗时同时带旧参数，保持 v1 兼容路径）。
- `App` 解析 `--zones` → 构造 `StartupOptions.Zones`；`HostWindow` 构造时 `ApplyTemplate(模板)` → 逐 zone `TryAttach(zoneId, hwnd)`。
- 同屏已有接管实例的拒绝重捕逻辑（`_captures`）不变。
- `AttachStartupTargets` 的 hwnd 直连路径保留（v1 语义），名字/PID 匹配路径只服务 zone 0/1。

## 7. 边界与风险

- **OS 最小宽钳制**：3 列布局每格 ~850px(2560 屏) 能装下多数窗口，但 6 区/窄 split 下 mspaint（704 DIP 最小宽）会探出格子——**接管前预检**：每 zone 目标宽度 ≥ 检测到的窗口当前宽度 × 0.8，不满足 → 整组拒绝并报因 `ZONE_TOO_NARROW`（宁可拒绝不做残废布局）。此阈值实测后调整。
- **最小窗口尺寸**：宿主 `MinWidth/MinHeight`（XAML）需按模板推 lower bound（最窄列 × 最少列数），`WndProc` 的 ptMinTrackSize 逻辑不变。
- **UIPI / Snap 浮层 / DeleteTab / DPI 两步走**：v1 机制全部原样生效，无新工作。
- **性能**：`Maintain` 250ms 遍历 N pane + N 次现场实测隐形边——6 格时约 6×250ms 内的 DwmGetWindowAttribute，可忽略（v1 已证 2 次开销无感）。
- **风险最大的单点**：`ApplyLayout`/`PaneRectDevice` 递归化的几何回归——v1 全部矩形断言测试是安全网，二格特例必须逐值不变（CI 现有 27+ 项全绿才准合入）。

## 8. 测试计划（新 `tools/tests/snap_templates_test.py` 等，入 run_all）

- 模板单元断言（C# 不可直接测，走黑盒）：`--template thirds-3 --zones` 接管 → 宿主矩形=工作区、各子窗 EFB≈zone 矩形（复用 efb_align 口径）。
- 分隔条拖动：田字拖横线/竖线，断言同层另一 split 不动、ratio 持久化。
- 释放/孤儿/隐藏释放：N 格各抽 1 例（复用 attach_heal 模式）。
- 检测器：thirds/quad/stack 合成靶窗（`tools/targets/snap_target.py` 扩展多窗编排）→ `--detect-snap` JSON 断言模板与映射。
- 二格兼容：现有 43+ 项全量回归零改动通过（红 = 重构破坏特例，打回）。
- 环境 SKIP 口径沿用 `pick_clean_monitor`（外来大窗污染检测场景）。

## 9. 交付分期

1. **T1 模板内核**：PaneTemplate + Pane + ApplyTemplate + 几何递归化 + 二格特例回归全绿（无新功能，纯重构，单独 commit）。
2. **T2 N 格交互**：分隔条泛化、拖入/替换/释放按 zone、状态栏/按钮适配、配置新格式+迁移。
3. **T3 检测与接管**：拓扑重建、`--zones` 链路、托盘放开 N 窗、ZONE_TOO_NARROW 预检、snap_templates_test。
4. **T4 收尾**：FEATURES.md 更新、AGENTS.md 记录实测坑、发布脚本冒烟（publish.py 无改动预期）。
