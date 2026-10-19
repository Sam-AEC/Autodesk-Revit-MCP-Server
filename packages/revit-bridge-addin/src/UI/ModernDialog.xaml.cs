using System;
using System.Diagnostics;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using RevitBridge;

namespace RevitBridge.UI
{
    public partial class ModernDialog : Window
    {
        private readonly Brush _bgBrush;
        private readonly Brush _cardBgBrush;
        private readonly Brush _textPrimaryBrush;
        private readonly Brush _textSecondaryBrush;
        private readonly Brush _borderBrush;
        private readonly Brush _headerBrush;
        private readonly Brush _footerBgBrush;
        private readonly Brush _footerBorderBrush;
        private readonly Brush _accentBrush;
        private readonly Brush _accentTextBrush;
        private readonly Brush _onAccentBrush;
        private readonly Color _accentColor;
        private readonly Color _successColor;
        private readonly Color _dangerColor;

        public ModernDialog()
        {
            // Detect Revit Theme
            bool isDark = false;
            try
            {
                isDark = Autodesk.Revit.UI.UIThemeManager.CurrentTheme == Autodesk.Revit.UI.UITheme.Dark;
            }
            catch
            {
                // Fallback if UIThemeManager is not available
            }

            // Same tokens as the panel (panel/styles.css, docs/design/tokens.md): one design across ribbon, panel and dialogs.
            SolidColorBrush Rgb(byte r, byte g, byte b) => new SolidColorBrush(Color.FromRgb(r, g, b));
            SolidColorBrush accent;
            if (isDark)
            {
                _bgBrush = Rgb(0x2D, 0x2D, 0x2D);
                _cardBgBrush = Rgb(0x36, 0x36, 0x36);
                _textPrimaryBrush = Rgb(0xED, 0xED, 0xED);
                _textSecondaryBrush = Rgb(0xBD, 0xBD, 0xBD);
                _borderBrush = Rgb(0x50, 0x50, 0x50);
                _headerBrush = Rgb(0x2B, 0x2B, 0x2B);
                _footerBgBrush = Rgb(0x36, 0x36, 0x36);
                _footerBorderBrush = Rgb(0x50, 0x50, 0x50);
                accent = Rgb(0x3F, 0xC3, 0xD6);
                _accentTextBrush = accent;
                _onAccentBrush = Rgb(0x06, 0x22, 0x2A);
                _successColor = Color.FromRgb(0x3F, 0xCB, 0x8B);
                _dangerColor = Color.FromRgb(0xFC, 0xAA, 0x9F);
            }
            else
            {
                _bgBrush = Rgb(0xF2, 0xF5, 0xF8);
                _cardBgBrush = Rgb(0xFF, 0xFF, 0xFF);
                _textPrimaryBrush = Rgb(0x18, 0x20, 0x2C);
                _textSecondaryBrush = Rgb(0x5B, 0x66, 0x76);
                _borderBrush = Rgb(0xD3, 0xDA, 0xE3);
                _headerBrush = Rgb(0x2B, 0x2B, 0x2B);
                _footerBgBrush = Rgb(0xE9, 0xEE, 0xF4);
                _footerBorderBrush = Rgb(0xD3, 0xDA, 0xE3);
                accent = Rgb(0x00, 0x91, 0xA7);
                _accentTextBrush = Rgb(0x04, 0x6B, 0x80);
                _onAccentBrush = Rgb(0xFF, 0xFF, 0xFF);
                _successColor = Color.FromRgb(0x12, 0x7A, 0x4B);
                _dangerColor = Color.FromRgb(0xC2, 0x3B, 0x2E);
            }

            _accentBrush = accent;
            _accentColor = accent.Color;

            // Expose as DynamicResources before initializing components so XAML bindings compile and evaluate perfectly
            Resources["BgBrush"] = _bgBrush;
            Resources["CardBgBrush"] = _cardBgBrush;
            Resources["TextPrimaryBrush"] = _textPrimaryBrush;
            Resources["TextSecondaryBrush"] = _textSecondaryBrush;
            Resources["BorderBrush"] = _borderBrush;
            Resources["HeaderBrush"] = _headerBrush;
            Resources["FooterBgBrush"] = _footerBgBrush;
            Resources["FooterBorderBrush"] = _footerBorderBrush;
            Resources["AccentBrush"] = _accentBrush;
            Resources["AccentTextBrush"] = _accentTextBrush;
            Resources["OnAccentBrush"] = _onAccentBrush;

            InitializeComponent();
            HeaderLogo.Source = BrandMark.CreateImageSource();
            Icon = BrandMark.CreateImageSource();

            // Keep dialogs usable on smaller displays and owned by Revit.
            var workArea = SystemParameters.WorkArea;
            MaxWidth = Math.Max(MinWidth, Math.Min(960, workArea.Width * 0.94));
            MaxHeight = Math.Max(MinHeight, Math.Min(860, workArea.Height * 0.92));
            Width = Math.Min(780, MaxWidth);
            Height = Math.Min(680, MaxHeight);

            var revitHandle = Process.GetCurrentProcess().MainWindowHandle;
            if (revitHandle != IntPtr.Zero)
            {
                new WindowInteropHelper(this).Owner = revitHandle;
            }

            // Enable dragging by clicking anywhere on the header
            MouseDown += (s, e) =>
            {
                if (e.ChangedButton == MouseButton.Left && e.GetPosition(this).Y < 64)
                {
                    DragMove();
                }
            };

            KeyDown += (s, e) =>
            {
                if (e.Key == Key.Escape)
                {
                    Close();
                }
            };
        }

        public void SetTitle(string title, string subtitle = "")
        {
            DialogTitle.Text = title;
            DialogSubtitle.Text = subtitle;
            if (string.IsNullOrEmpty(subtitle))
            {
                DialogSubtitle.Visibility = Visibility.Collapsed;
            }
        }

        // Glyphs are drawn in a 24 x 24 box: stroke only, round caps, like the ribbon and panel icons.
        private FrameworkElement CreateGlyphTile(string icon, double tile)
        {
            // Semantic keys ("success", "stop", ...) are the contract; the emoji are accepted for old callers.
            string? data = null;
            Color kind = _accentColor;
            string key = icon.Trim().ToLowerInvariant();
            if (key == "success" || icon.Contains("\u2705")) { data = "M5,12.5 L10,17.5 L19,7.5"; kind = _successColor; }
            else if (key == "stop" || icon.Contains("\U0001F6D1")) { data = "M7,7 H17 V17 H7 Z"; kind = _dangerColor; }
            else if (key == "error" || icon.Contains("\u274C")) { data = "M7,7 L17,17 M17,7 L7,17"; kind = _dangerColor; }
            else if (key == "info" || icon.Contains("\u2139")) { data = "M12,10.5 V17 M12,6.6 V6.5"; }
            else if (key == "plug" || icon.Contains("\U0001F50C")) { data = "M8,4 V9 M16,4 V9 M6,9 H18 V12 A6,6 0 0 1 6,12 Z M12,18 V21"; }
            else if (key == "chart" || icon.Contains("\U0001F4CA")) { data = "M6,19 V12 M12,19 V6 M18,19 V10"; }
            else if (key == "clock" || icon.Contains("\u23F1")) { data = "M12,4 A8,8 0 1 0 12,20 A8,8 0 1 0 12,4 M12,8 V12.5 L15,14.5"; }

            // Short plain text ("MCP", "API") renders as a chip; any other unknown symbol falls back to the info glyph.
            bool chip = data == null && icon.Length <= 6 && icon.All(ch => ch < 0x2000);
            if (data == null && !chip)
            {
                data = "M12,10.5 V17 M12,6.6 V6.5";
            }

            var border = new Border
            {
                Width = tile,
                Height = tile,
                CornerRadius = new CornerRadius(10),
                Background = new SolidColorBrush(Color.FromArgb(0x29, kind.R, kind.G, kind.B)),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center
            };

            if (data != null)
            {
                var canvas = new Canvas { Width = 24, Height = 24 };
                canvas.Children.Add(new System.Windows.Shapes.Path
                {
                    Data = Geometry.Parse(data),
                    Stroke = new SolidColorBrush(kind),
                    StrokeThickness = 2.4,
                    StrokeStartLineCap = PenLineCap.Round,
                    StrokeEndLineCap = PenLineCap.Round,
                    StrokeLineJoin = PenLineJoin.Round
                });
                border.Child = new Viewbox { Width = tile * 0.55, Height = tile * 0.55, Child = canvas };
            }
            else
            {
                border.Width = double.NaN;
                border.MinWidth = tile;
                border.Padding = new Thickness(8, 0, 8, 0);
                border.Child = new TextBlock
                {
                    Text = icon,
                    FontSize = 11,
                    FontWeight = FontWeights.Bold,
                    Foreground = (Brush)FindResource("AccentTextBrush"),
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center
                };
            }

            return border;
        }

        /// <param name="icon">Semantic key: success, stop, error, info, plug, chart, clock.</param>
        public void AddStatusCard(string icon, string label, string value)
        {
            var card = new Border
            {
                Style = (Style)FindResource("StatCard"),
                MinHeight = 60
            };

            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(50) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            // Icon tile (vector glyph in the shared icon language; colour follows the glyph kind)
            var iconText = CreateGlyphTile(icon, 44);
            Grid.SetColumn(iconText, 0);
            grid.Children.Add(iconText);

            // Text Stack
            var textStack = new StackPanel
            {
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(10, 0, 0, 0)
            };

            var labelText = new TextBlock
            {
                Text = label,
                FontSize = 12,
                Foreground = (Brush)FindResource("TextSecondaryBrush"),
                Margin = new Thickness(0, 0, 0, 5),
                TextWrapping = TextWrapping.Wrap
            };

            var valueText = new TextBlock
            {
                Text = value,
                FontSize = 18,
                FontWeight = FontWeights.SemiBold,
                Foreground = (Brush)FindResource("TextPrimaryBrush"),
                TextWrapping = TextWrapping.Wrap
            };

            textStack.Children.Add(labelText);
            textStack.Children.Add(valueText);
            Grid.SetColumn(textStack, 1);
            grid.Children.Add(textStack);

            card.Child = grid;
            ContentPanel.Children.Add(card);
        }

                public void AddBrandStatusCard(string label, string value)
        {
            var card = new Border
            {
                Style = (Style)FindResource("StatCard"),
                MinHeight = 60
            };

            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(50) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            // Brand mark (shared with the dialog header and ribbon brand icon)
            var viewBox = BrandMark.CreateImage(40);

            Grid.SetColumn(viewBox, 0);
            grid.Children.Add(viewBox);

            var textStack = new StackPanel
            {
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(10, 0, 0, 0)
            };

            var labelText = new TextBlock
            {
                Text = label,
                FontSize = 12,
                Foreground = (Brush)FindResource("TextSecondaryBrush"),
                Margin = new Thickness(0, 0, 0, 5),
                TextWrapping = TextWrapping.Wrap
            };

            var valueText = new TextBlock
            {
                Text = value,
                FontSize = 18,
                FontWeight = FontWeights.SemiBold,
                Foreground = (Brush)FindResource("TextPrimaryBrush"),
                TextWrapping = TextWrapping.Wrap
            };

            textStack.Children.Add(labelText);
            textStack.Children.Add(valueText);
            Grid.SetColumn(textStack, 1);
            grid.Children.Add(textStack);

            card.Child = grid;
            ContentPanel.Children.Add(card);
        }

        public void AddInfoSection(string title, string content)
        {
            var section = new StackPanel { Margin = new Thickness(0, 10, 0, 10) };

            var titleText = new TextBlock
            {
                Text = title,
                FontSize = 14,
                FontWeight = FontWeights.SemiBold,
                Foreground = (Brush)FindResource("TextPrimaryBrush"),
                Margin = new Thickness(0, 0, 0, 8)
            };

            var contentBorder = new Border
            {
                Background = (Brush)FindResource("CardBgBrush"),
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(14),
                BorderBrush = (Brush)FindResource("BorderBrush"),
                BorderThickness = new Thickness(1)
            };

            var contentText = new TextBlock
            {
                Text = content,
                FontSize = 13,
                Foreground = (Brush)FindResource("TextSecondaryBrush"),
                TextWrapping = TextWrapping.Wrap,
                LineHeight = 20
            };

            contentBorder.Child = contentText;
            section.Children.Add(titleText);
            section.Children.Add(contentBorder);
            ContentPanel.Children.Add(section);
        }

        public void AddStatsGrid(params (string icon, string label, string value)[] stats)
        {
            var grid = new Grid { Margin = new Thickness(0, 10, 0, 0) };

            int columns = Math.Min(stats.Length, 3);
            for (int i = 0; i < columns; i++)
            {
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            }

            for (int i = 0; i < stats.Length; i++)
            {
                var stat = stats[i];
                var card = CreateStatCard(stat.icon, stat.label, stat.value);
                Grid.SetColumn(card, i % columns);
                Grid.SetRow(card, i / columns);

                if (i / columns >= grid.RowDefinitions.Count)
                {
                    grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                }

                grid.Children.Add(card);
            }

            ContentPanel.Children.Add(grid);
        }

        private Border CreateStatCard(string icon, string label, string value)
        {
            var card = new Border
            {
                Style = (Style)FindResource("StatCard")
            };

            var stack = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center };

            var iconText = CreateGlyphTile(icon, 36);
            iconText.Margin = new Thickness(0, 0, 0, 10);

            var valueText = new TextBlock
            {
                Text = value,
                FontSize = 20,
                FontWeight = FontWeights.Bold,
                HorizontalAlignment = HorizontalAlignment.Center,
                TextAlignment = TextAlignment.Center,
                TextWrapping = TextWrapping.Wrap,
                Foreground = (Brush)FindResource("AccentTextBrush"),
                Margin = new Thickness(0, 0, 0, 4)
            };

            var labelText = new TextBlock
            {
                Text = label,
                FontSize = 11,
                HorizontalAlignment = HorizontalAlignment.Center,
                TextAlignment = TextAlignment.Center,
                TextWrapping = TextWrapping.Wrap,
                Foreground = (Brush)FindResource("TextSecondaryBrush")
            };

            stack.Children.Add(iconText);
            stack.Children.Add(valueText);
            stack.Children.Add(labelText);

            card.Child = stack;
            return card;
        }

        public void AddSeparator()
        {
            var separator = new Border
            {
                Height = 1,
                Background = (Brush)FindResource("BorderBrush"),
                Margin = new Thickness(0, 15, 0, 15)
            };
            ContentPanel.Children.Add(separator);
        }

        public void AddLinkButtons(params (string label, string url)[] links)
        {
            var panel = new WrapPanel
            {
                Margin = new Thickness(0, 8, 0, 8),
                HorizontalAlignment = HorizontalAlignment.Left
            };

            foreach (var link in links)
            {
                var button = new Button
                {
                    Content = link.label,
                    Style = (Style)FindResource("SecondaryButton"),
                    Padding = new Thickness(14, 7, 14, 7),
                    Margin = new Thickness(0, 0, 8, 8),
                    ToolTip = link.url
                };
                button.Click += (s, e) =>
                {
                    OpenLink(link.url);
                };
                panel.Children.Add(button);
            }

            ContentPanel.Children.Add(panel);
        }

        public void AddProfileSection(
            string name,
            string title,
            string email,
            string gitHubUrl,
            string linkedInUrl)
        {
            var card = new Border
            {
                Style = (Style)FindResource("StatCard"),
                Padding = new Thickness(18),
                Margin = new Thickness(0, 10, 0, 10)
            };

            var layout = new Grid();
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(58) });
            layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            var initials = new Border
            {
                Width = 46,
                Height = 46,
                CornerRadius = new CornerRadius(23),
                Background = (Brush)FindResource("AccentBrush"),
                VerticalAlignment = VerticalAlignment.Top
            };
            initials.Child = new TextBlock
            {
                Text = "SM",
                Foreground = (Brush)FindResource("OnAccentBrush"),
                FontSize = 15,
                FontWeight = FontWeights.Bold,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center
            };
            layout.Children.Add(initials);

            var details = new StackPanel();
            Grid.SetColumn(details, 1);

            details.Children.Add(new TextBlock
            {
                Text = name,
                FontSize = 16,
                FontWeight = FontWeights.SemiBold,
                Foreground = (Brush)FindResource("TextPrimaryBrush"),
                TextWrapping = TextWrapping.Wrap
            });
            details.Children.Add(new TextBlock
            {
                Text = title,
                FontSize = 12,
                Margin = new Thickness(0, 3, 0, 2),
                Foreground = (Brush)FindResource("TextSecondaryBrush"),
                TextWrapping = TextWrapping.Wrap
            });
            details.Children.Add(new TextBlock
            {
                Text = email,
                FontSize = 11,
                Foreground = (Brush)FindResource("TextSecondaryBrush"),
                TextWrapping = TextWrapping.Wrap
            });

            var buttons = new WrapPanel { Margin = new Thickness(0, 12, 0, 0) };
            buttons.Children.Add(CreateProfileButton(
                "Email",
                $"mailto:{email}",
                Colors.Transparent));
            buttons.Children.Add(CreateProfileButton(
                "GitHub",
                gitHubUrl,
                Colors.Transparent));
            buttons.Children.Add(CreateProfileButton(
                "LinkedIn",
                linkedInUrl,
                Colors.Transparent));
            details.Children.Add(buttons);

            layout.Children.Add(details);
            card.Child = layout;
            ContentPanel.Children.Add(card);
        }

        private Button CreateProfileButton(string label, string url, Color background)
        {
            var button = new Button
            {
                Content = label,
                Style = (Style)FindResource("SecondaryButton"),
                Padding = new Thickness(14, 7, 14, 7),
                Margin = new Thickness(0, 0, 8, 8),
                ToolTip = url
            };
            button.Click += (s, e) =>
            {
                OpenLink(url);
            };
            return button;
        }

        private void OpenLink(string url)
        {
            if (ProductInfo.TryOpenUrl(url, out var error))
            {
                return;
            }

            var notice = new ModernDialog { Owner = this };
            notice.SetTitle(ProductInfo.ProductName, "Could not open the link");
            notice.AddStatusCard("error", "Link", "Your system could not open this address.");
            notice.AddInfoSection("Address", url);
            if (!string.IsNullOrWhiteSpace(error))
            {
                notice.AddInfoSection("Details", error);
            }

            notice.SetActionButton("OK");
            notice.ShowDialog();
        }

        public void SetActionButton(string text, Action? action = null)
        {
            ActionButton.Content = text;
            if (action != null)
            {
                ActionButton.Click += (s, e) =>
                {
                    action();
                    Close();
                };
            }
        }

        public void ShowCancelButton(Action? action = null)
        {
            CancelButton.Visibility = Visibility.Visible;
            if (action != null)
            {
                CancelButton.Click += (s, e) =>
                {
                    action();
                    Close();
                };
            }
        }

        private void CloseButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private void ActionButton_Click(object sender, RoutedEventArgs e)
        {
            DialogResult = true;
            Close();
        }

        private void CancelButton_Click(object sender, RoutedEventArgs e)
        {
            DialogResult = false;
            Close();
        }
    }
}
