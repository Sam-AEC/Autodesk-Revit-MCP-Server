using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace RevitBridge.UI
{
    public partial class ModernDialog : Window
    {
        public ModernDialog()
        {
            InitializeComponent();

            // Enable dragging by clicking anywhere on the header
            MouseDown += (s, e) =>
            {
                if (e.ChangedButton == MouseButton.Left && e.GetPosition(this).Y < 60)
                {
                    DragMove();
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

        public void AddStatusCard(string icon, string label, string value, Brush? iconColor = null)
        {
            var card = new Border
            {
                Style = (Style)FindResource("StatCard"),
                MinHeight = 60
            };

            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(50) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            // Icon
            var iconText = new TextBlock
            {
                Text = icon,
                FontSize = 32,
                VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Center,
                Foreground = iconColor ?? new SolidColorBrush(Color.FromRgb(33, 150, 243))
            };
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
                Foreground = new SolidColorBrush(Color.FromRgb(117, 117, 117)),
                Margin = new Thickness(0, 0, 0, 5)
            };

            var valueText = new TextBlock
            {
                Text = value,
                FontSize = 18,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(Color.FromRgb(33, 33, 33))
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
                Foreground = new SolidColorBrush(Color.FromRgb(66, 66, 66)),
                Margin = new Thickness(0, 0, 0, 8)
            };

            var contentBorder = new Border
            {
                Background = new SolidColorBrush(Color.FromRgb(250, 250, 250)),
                CornerRadius = new CornerRadius(4),
                Padding = new Thickness(12),
                BorderBrush = new SolidColorBrush(Color.FromRgb(224, 224, 224)),
                BorderThickness = new Thickness(1)
            };

            var contentText = new TextBlock
            {
                Text = content,
                FontSize = 12,
                Foreground = new SolidColorBrush(Color.FromRgb(97, 97, 97)),
                TextWrapping = TextWrapping.Wrap,
                FontFamily = new FontFamily("Consolas")
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
                Background = Brushes.White,
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(15),
                Margin = new Thickness(5),
                Effect = new System.Windows.Media.Effects.DropShadowEffect
                {
                    Color = Colors.Black,
                    Opacity = 0.1,
                    BlurRadius = 10,
                    ShadowDepth = 2
                }
            };

            var stack = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center };

            var iconText = new TextBlock
            {
                Text = icon,
                FontSize = 28,
                HorizontalAlignment = HorizontalAlignment.Center,
                Margin = new Thickness(0, 0, 0, 8)
            };

            var valueText = new TextBlock
            {
                Text = value,
                FontSize = 20,
                FontWeight = FontWeights.Bold,
                HorizontalAlignment = HorizontalAlignment.Center,
                Foreground = new SolidColorBrush(Color.FromRgb(33, 150, 243)),
                Margin = new Thickness(0, 0, 0, 4)
            };

            var labelText = new TextBlock
            {
                Text = label,
                FontSize = 11,
                HorizontalAlignment = HorizontalAlignment.Center,
                Foreground = new SolidColorBrush(Color.FromRgb(117, 117, 117))
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
                Background = new SolidColorBrush(Color.FromRgb(224, 224, 224)),
                Margin = new Thickness(0, 15, 0, 15)
            };
            ContentPanel.Children.Add(separator);
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
