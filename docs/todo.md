# TODO — v2 宿主模板化（任意 snap 布局）

详细设计见 [design-v2-templates.md](design-v2-templates.md)（各条目括号引用其章节；完成即勾销）。

## T1 模板内核（纯重构，二格特例回归全绿为合入门禁）

- [ ] PaneTemplate 数据结构：二分树（Zone/Split 节点）+ 内置模板目录 + ZoneId 先序稳定分配（§2.1）
- [ ] Pane 抽象替代 `_left/_right`：`List<Pane>` + zone 索引，ChildAt/HwndOf/IsAttachedChild/UpdateStatus 泛化（§3.1）
- [ ] 宿主视觉树动态生成：XAML 静态外壳保留，`_content` 内 Grid 按 Split 树代码生成，分隔条样式复用 DividerStyle（§2.2）
- [ ] 几何递归化：UpdatePaneWidths/ApplyLayout/PaneRectDevice 按 Split 树求各 zone 设备矩形（§3.3）
- [ ] 二格降级为 `binary-50` 特例，存量 43+ 项回归零改动通过（§7/§8）

## T2 N 格交互

- [ ] 分隔条泛化：每根分隔绑定自身 SplitNode，拖动只改该 Ratio（clamp [0.15,0.85]），田字十字两条独立（§3.3）
- [ ] 拖入/替换/换格/释放按 zoneId：TryAttach 分支泛化、HitTestPaneAt/HitTestSlot/SetDragHighlight 返回 zoneId（§3.1/§3.3）
- [ ] SwapSides 保留为二格特例按钮（非 binary 模板隐藏）；顶条侧按钮只服务前两 zone（§3.1）
- [ ] 配置新格式：Template + Splits（树路径→ratio）+ AttachedHwnds 变长；旧 Ratio 字段迁移读取（§5）
- [ ] 空格占位提示/吸附格透明规则逐 zone 保持（§2.2）

## T3 检测与接管

- [ ] 检测器拓扑重建：共享边合并 → 递归二分拟合 → PaneTemplate + zone→hwnd 映射；STACKED 报因移除（上下排列成合法模板）（§4）
- [ ] `--detect-snap` JSON 扩展模板与映射字段（v1 二窗字段保持兼容输出）（§4）
- [ ] `--template/--zones` CLI + 托盘 Capture 放开 N 窗接管（二窗双参数兼容）（§6）
- [ ] 接管预检 ZONE_TOO_NARROW：zone 目标宽 < 窗口当前宽 × 0.8 整组拒绝报因（§7）
- [ ] HostWindow 最小尺寸按模板推 lower bound（§7）

## T4 测试与收尾

- [ ] snap_templates_test：多模板接管黑盒（宿主=工作区、子窗 EFB≈zone）、田字分隔拖动、N 格释放/孤儿抽样，入 run_all（§8）
- [ ] config_edge_test 增补：新格式读取、旧格式迁移、坏 Template 回退（§5/§8）
- [ ] 多窗编排扩展 snap_target.py（一次拉起 N 个指定几何靶窗）（§8）
- [ ] FEATURES.md / AGENTS.md 更新；发布冒烟（§9）
