using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace WindowMerger;

/// <summary>
/// 更新确认对话框：全主题化（AppTheme 调色板快照）——系统 MessageBox 不随深浅色主题，
/// 与全主题化 UI 冲突（ToolTip 因此整体换过模板，同款考量）。模态、居中于宿主，
/// Enter=确认（IsDefault）、Esc=取消（IsCancel）；按钮 AutomationId 供 e2e 测试定位。
/// 对话框生命周期内主题不会变（模态期间宿主按钮点不到），直接用调色板快照的静态画刷。
/// </summary>
public sealed class UpdateDialog : Window
{
    public UpdateDialog(string headline, string detail, string confirmText)
    {
        var p = AppTheme.Current();
        WindowStyle = WindowStyle.None;
        AllowsTransparency = true;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        SizeToContent = SizeToContent.WidthAndHeight;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = Brushes.Transparent;

        var body = new StackPanel { Margin = new Thickness(18) };
        body.Children.Add(new TextBlock
        {
            Text = headline,
            FontSize = 14,
            FontWeight = FontWeights.SemiBold,
            Foreground = AppTheme.Brush(p.Text),
        });
        body.Children.Add(new TextBlock
        {
            Text = detail,
            FontSize = 12,
            TextWrapping = TextWrapping.Wrap,
            MaxWidth = 330,
            Margin = new Thickness(0, 8, 0, 0),
            Foreground = AppTheme.Brush(p.Text),
        });

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 16, 0, 0),
        };
        var confirm = DialogButton(confirmText, primary: true, p, "UpdateConfirm");
        confirm.IsDefault = true; // Enter 确认
        confirm.Click += (_, _) => DialogResult = true;
        var cancel = DialogButton("取消", primary: false, p, "UpdateCancel");
        cancel.IsCancel = true; // Esc 取消，点击自动 DialogResult=false
        buttons.Children.Add(confirm);
        buttons.Children.Add(cancel);
        body.Children.Add(buttons);

        Content = new Border
        {
            Background = AppTheme.Brush(p.Bar),
            BorderBrush = AppTheme.Brush(p.Border),
            BorderThickness = new Thickness(1),
            Child = body,
        };
    }

    /// <summary>极简按钮（Border+ContentPresenter，同顶条模式）：主按钮用强调色底。
    /// 悬停刷色走 Trigger——Background 只能由 Style Setter 提供，本地赋值优先级高于
    /// Trigger 会让悬停失效（依赖属性优先级规则）；此处是快照静态画刷，无 DynamicResource
    /// 引用销毁陷阱。</summary>
    private static Button DialogButton(string text, bool primary, AppTheme.Palette p, string automationId)
    {
        var template = new ControlTemplate(typeof(Button));
        var border = new FrameworkElementFactory(typeof(Border));
        border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(Button.BackgroundProperty));
        border.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(Button.BorderBrushProperty));
        border.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(Button.BorderThicknessProperty));
        border.SetValue(Border.CornerRadiusProperty, new CornerRadius(2));
        border.SetValue(Border.PaddingProperty, new Thickness(12, 6, 12, 6));
        var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
        presenter.SetValue(ContentPresenter.HorizontalAlignmentProperty, HorizontalAlignment.Center);
        presenter.SetValue(ContentPresenter.VerticalAlignmentProperty, VerticalAlignment.Center);
        border.AppendChild(presenter);
        template.VisualTree = border;

        var style = new Style(typeof(Button));
        style.Setters.Add(new Setter(BackgroundProperty,
            primary ? AppTheme.Brush(p.DividerHover) : Brushes.Transparent));
        var hover = new Trigger { Property = Button.IsMouseOverProperty, Value = true };
        hover.Setters.Add(new Setter(BackgroundProperty, primary
            ? Lighten(((SolidColorBrush)AppTheme.Brush(p.DividerHover)).Color)
            : AppTheme.Brush(p.ButtonHover)));
        style.Triggers.Add(hover);

        var b = new Button
        {
            Content = text,
            MinWidth = 88,
            Margin = new Thickness(8, 0, 0, 0),
            FontSize = 12,
            Cursor = Cursors.Hand,
            Foreground = AppTheme.Brush(p.Text), // 强调底色两种主题下都与文字色对比足够（实测配色）
            BorderBrush = AppTheme.Brush(p.Border),
            BorderThickness = new Thickness(1),
            Template = template,
            Style = style,
        };
        b.SetValue(System.Windows.Automation.AutomationProperties.AutomationIdProperty, automationId);
        return b;
    }

    private static SolidColorBrush Lighten(Color c)
    {
        var lighter = Color.FromRgb(
            (byte)(c.R + (255 - c.R) * 30 / 100),
            (byte)(c.G + (255 - c.G) * 30 / 100),
            (byte)(c.B + (255 - c.B) * 30 / 100));
        var brush = new SolidColorBrush(lighter);
        brush.Freeze();
        return brush;
    }
}
