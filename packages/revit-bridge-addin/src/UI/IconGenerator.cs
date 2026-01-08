using System;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace RevitBridge.UI
{
    /// <summary>
    /// Generates icon images for Revit ribbon buttons
    /// </summary>
    public static class IconGenerator
    {
        /// <summary>
        /// Creates a Connect icon (green play button with network)
        /// </summary>
        public static BitmapSource CreateConnectIcon(int size = 32)
        {
            var visual = new DrawingVisual();
            using (var context = visual.RenderOpen())
            {
                // Background circle
                var greenBrush = new SolidColorBrush(Color.FromRgb(76, 175, 80)); // Material Green
                context.DrawEllipse(greenBrush, null, new Point(size / 2.0, size / 2.0), size / 2.0, size / 2.0);

                // Play/Connect symbol (white)
                var whiteBrush = Brushes.White;
                var geometry = new PathGeometry();
                var figure = new PathFigure { StartPoint = new Point(size * 0.35, size * 0.25) };
                figure.Segments.Add(new LineSegment(new Point(size * 0.35, size * 0.75), true));
                figure.Segments.Add(new LineSegment(new Point(size * 0.75, size * 0.5), true));
                figure.IsClosed = true;
                geometry.Figures.Add(figure);
                context.DrawGeometry(whiteBrush, null, geometry);

                // Small network dots
                double dotSize = size * 0.08;
                context.DrawEllipse(whiteBrush, null, new Point(size * 0.15, size * 0.15), dotSize, dotSize);
                context.DrawEllipse(whiteBrush, null, new Point(size * 0.85, size * 0.15), dotSize, dotSize);
                context.DrawEllipse(whiteBrush, null, new Point(size * 0.85, size * 0.85), dotSize, dotSize);
            }

            return RenderVisual(visual, size, size);
        }

        /// <summary>
        /// Creates a Disconnect icon (red stop button)
        /// </summary>
        public static BitmapSource CreateDisconnectIcon(int size = 32)
        {
            var visual = new DrawingVisual();
            using (var context = visual.RenderOpen())
            {
                // Background circle
                var redBrush = new SolidColorBrush(Color.FromRgb(244, 67, 54)); // Material Red
                context.DrawEllipse(redBrush, null, new Point(size / 2.0, size / 2.0), size / 2.0, size / 2.0);

                // Stop square (white)
                var whiteBrush = Brushes.White;
                var rect = new Rect(size * 0.3, size * 0.3, size * 0.4, size * 0.4);
                context.DrawRectangle(whiteBrush, null, rect);
            }

            return RenderVisual(visual, size, size);
        }

        /// <summary>
        /// Creates a Status icon (blue info with chart)
        /// </summary>
        public static BitmapSource CreateStatusIcon(int size = 32)
        {
            var visual = new DrawingVisual();
            using (var context = visual.RenderOpen())
            {
                // Background circle
                var blueBrush = new SolidColorBrush(Color.FromRgb(33, 150, 243)); // Material Blue
                context.DrawEllipse(blueBrush, null, new Point(size / 2.0, size / 2.0), size / 2.0, size / 2.0);

                // Info symbol (white) - combination of 'i' and chart bars
                var whiteBrush = Brushes.White;
                var whitePen = new Pen(whiteBrush, size * 0.06);

                // Chart bars
                double barWidth = size * 0.12;
                double spacing = size * 0.08;
                double startX = size * 0.25;
                double baseY = size * 0.7;

                // Three bars of different heights
                context.DrawRectangle(whiteBrush, null, new Rect(startX, baseY - size * 0.15, barWidth, size * 0.15));
                context.DrawRectangle(whiteBrush, null, new Rect(startX + barWidth + spacing, baseY - size * 0.25, barWidth, size * 0.25));
                context.DrawRectangle(whiteBrush, null, new Rect(startX + (barWidth + spacing) * 2, baseY - size * 0.35, barWidth, size * 0.35));
            }

            return RenderVisual(visual, size, size);
        }

        /// <summary>
        /// Creates a Settings icon (gear)
        /// </summary>
        public static BitmapSource CreateSettingsIcon(int size = 32)
        {
            var visual = new DrawingVisual();
            using (var context = visual.RenderOpen())
            {
                // Background circle
                var grayBrush = new SolidColorBrush(Color.FromRgb(96, 125, 139)); // Material Blue Gray
                context.DrawEllipse(grayBrush, null, new Point(size / 2.0, size / 2.0), size / 2.0, size / 2.0);

                // Gear shape (simplified)
                var whiteBrush = Brushes.White;
                double centerX = size / 2.0;
                double centerY = size / 2.0;
                double outerRadius = size * 0.35;
                double innerRadius = size * 0.15;
                int teeth = 8;

                var geometry = new PathGeometry();
                var figure = new PathFigure();

                for (int i = 0; i < teeth; i++)
                {
                    double angle1 = (Math.PI * 2 * i) / teeth;
                    double angle2 = (Math.PI * 2 * (i + 0.4)) / teeth;
                    double angle3 = (Math.PI * 2 * (i + 0.6)) / teeth;
                    double angle4 = (Math.PI * 2 * (i + 1)) / teeth;

                    Point p1 = new Point(centerX + outerRadius * Math.Cos(angle1), centerY + outerRadius * Math.Sin(angle1));
                    Point p2 = new Point(centerX + outerRadius * Math.Cos(angle2), centerY + outerRadius * Math.Sin(angle2));
                    Point p3 = new Point(centerX + innerRadius * Math.Cos(angle3), centerY + innerRadius * Math.Sin(angle3));
                    Point p4 = new Point(centerX + innerRadius * Math.Cos(angle4), centerY + innerRadius * Math.Sin(angle4));

                    if (i == 0)
                        figure.StartPoint = p1;

                    figure.Segments.Add(new LineSegment(p2, true));
                    figure.Segments.Add(new LineSegment(p3, true));
                    figure.Segments.Add(new LineSegment(p4, true));
                }

                figure.IsClosed = true;
                geometry.Figures.Add(figure);
                context.DrawGeometry(whiteBrush, null, geometry);

                // Center hole
                context.DrawEllipse(grayBrush, null, new Point(centerX, centerY), size * 0.12, size * 0.12);
            }

            return RenderVisual(visual, size, size);
        }

        /// <summary>
        /// Creates a generic RevitMCP icon (branded)
        /// </summary>
        public static BitmapSource CreateBrandIcon(int size = 32)
        {
            var visual = new DrawingVisual();
            using (var context = visual.RenderOpen())
            {
                // Gradient background
                var gradient = new LinearGradientBrush(
                    Color.FromRgb(33, 150, 243),
                    Color.FromRgb(21, 101, 192),
                    45);
                context.DrawRectangle(gradient, null, new Rect(0, 0, size, size));

                // 3D cube representing Revit model
                var whiteBrush = Brushes.White;
                var whitePen = new Pen(whiteBrush, size * 0.04);

                // Front face
                Point p1 = new Point(size * 0.3, size * 0.5);
                Point p2 = new Point(size * 0.7, size * 0.5);
                Point p3 = new Point(size * 0.7, size * 0.8);
                Point p4 = new Point(size * 0.3, size * 0.8);

                var frontFace = new PathGeometry();
                var frontFigure = new PathFigure { StartPoint = p1, IsClosed = true };
                frontFigure.Segments.Add(new LineSegment(p2, true));
                frontFigure.Segments.Add(new LineSegment(p3, true));
                frontFigure.Segments.Add(new LineSegment(p4, true));
                frontFace.Figures.Add(frontFigure);
                context.DrawGeometry(whiteBrush, whitePen, frontFace);

                // Top face
                Point p5 = new Point(size * 0.5, size * 0.25);
                Point p6 = new Point(size * 0.9, size * 0.25);
                var topFace = new PathGeometry();
                var topFigure = new PathFigure { StartPoint = p5, IsClosed = true };
                topFigure.Segments.Add(new LineSegment(p6, true));
                topFigure.Segments.Add(new LineSegment(p2, true));
                topFigure.Segments.Add(new LineSegment(p1, true));
                topFace.Figures.Add(topFigure);
                var topBrush = new SolidColorBrush(Color.FromArgb(180, 255, 255, 255));
                context.DrawGeometry(topBrush, whitePen, topFace);

                // Right face
                var rightFace = new PathGeometry();
                var rightFigure = new PathFigure { StartPoint = p2, IsClosed = true };
                rightFigure.Segments.Add(new LineSegment(p6, true));
                rightFigure.Segments.Add(new LineSegment(new Point(size * 0.9, size * 0.55), true));
                rightFigure.Segments.Add(new LineSegment(p3, true));
                rightFace.Figures.Add(rightFigure);
                var rightBrush = new SolidColorBrush(Color.FromArgb(150, 255, 255, 255));
                context.DrawGeometry(rightBrush, whitePen, rightFace);
            }

            return RenderVisual(visual, size, size);
        }

        private static BitmapSource RenderVisual(DrawingVisual visual, int width, int height)
        {
            var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(visual);
            bitmap.Freeze();
            return bitmap;
        }

        /// <summary>
        /// Saves an icon to a file
        /// </summary>
        public static void SaveIcon(BitmapSource icon, string filePath)
        {
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(icon));

            Directory.CreateDirectory(Path.GetDirectoryName(filePath) ?? "");

            using (var stream = new FileStream(filePath, FileMode.Create))
            {
                encoder.Save(stream);
            }
        }
    }
}
