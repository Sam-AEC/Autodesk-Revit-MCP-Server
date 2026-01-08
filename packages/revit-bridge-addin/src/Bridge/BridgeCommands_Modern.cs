using System;
using System.Windows.Media;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevitBridge.UI;

namespace RevitBridge.Bridge
{
    [Transaction(TransactionMode.Manual)]
    public class CommandConnect : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            if (App.Server != null)
            {
                if (!App.Server.IsListening)
                {
                    App.Server.Start();
                    ShowSuccessDialog("Server Connected", "The MCP Bridge Server is now running and ready to accept connections.");
                }
                else
                {
                    ShowInfoDialog("Already Connected", "The MCP Bridge Server is already running.");
                }
            }
            return Result.Succeeded;
        }

        private void ShowSuccessDialog(string title, string message)
        {
            var dialog = new ModernDialog();
            dialog.SetTitle(title, "Success");

            dialog.AddStatusCard(
                "✅",
                "Status",
                message,
                new SolidColorBrush(Color.FromRgb(76, 175, 80))
            );

            dialog.AddInfoSection("Server Address", "http://localhost:3000/");

            dialog.SetActionButton("Great!");
            dialog.ShowDialog();
        }

        private void ShowInfoDialog(string title, string message)
        {
            var dialog = new ModernDialog();
            dialog.SetTitle(title, "Information");

            dialog.AddStatusCard(
                "ℹ️",
                "Status",
                message,
                new SolidColorBrush(Color.FromRgb(33, 150, 243))
            );

            dialog.SetActionButton("OK");
            dialog.ShowDialog();
        }
    }

    [Transaction(TransactionMode.Manual)]
    public class CommandDisconnect : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            if (App.Server != null)
            {
                if (App.Server.IsListening)
                {
                    App.Server.Stop();
                    ShowDisconnectDialog();
                }
                else
                {
                    ShowInfoDialog("Already Disconnected", "The Bridge Server is not running.");
                }
            }
            return Result.Succeeded;
        }

        private void ShowDisconnectDialog()
        {
            var dialog = new ModernDialog();
            dialog.SetTitle("Server Disconnected", "Connection Closed");

            dialog.AddStatusCard(
                "🛑",
                "Status",
                "The MCP Bridge Server has been stopped.",
                new SolidColorBrush(Color.FromRgb(244, 67, 54))
            );

            dialog.AddInfoSection("Note", "You can restart the server anytime by clicking the Connect button.");

            dialog.SetActionButton("OK");
            dialog.ShowDialog();
        }

        private void ShowInfoDialog(string title, string message)
        {
            var dialog = new ModernDialog();
            dialog.SetTitle(title, "Information");

            dialog.AddStatusCard(
                "ℹ️",
                "Status",
                message,
                new SolidColorBrush(Color.FromRgb(33, 150, 243))
            );

            dialog.SetActionButton("OK");
            dialog.ShowDialog();
        }
    }

    [Transaction(TransactionMode.Manual)]
    public class CommandStatus : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            if (App.Server == null)
            {
                ShowErrorDialog();
                return Result.Failed;
            }

            ShowStatusDialog(commandData);
            return Result.Succeeded;
        }

        private void ShowStatusDialog(ExternalCommandData commandData)
        {
            var doc = commandData.Application.ActiveUIDocument?.Document;

            var dialog = new ModernDialog();
            dialog.SetTitle(
                "RevitMCP Bridge Status",
                App.Server!.IsRunning ? "Server is Active" : "Server is Stopped"
            );

            // Status indicator
            string statusIcon = App.Server.IsRunning ? "✅" : "🛑";
            string statusText = App.Server.IsRunning ? "Running" : "Stopped";
            var statusColor = App.Server.IsRunning
                ? new SolidColorBrush(Color.FromRgb(76, 175, 80))
                : new SolidColorBrush(Color.FromRgb(244, 67, 54));

            dialog.AddStatusCard(statusIcon, "Server Status", statusText, statusColor);

            // Statistics Grid
            dialog.AddStatsGrid(
                ("🔌", "Connections", App.Server.ActiveConnections.ToString()),
                ("📊", "Total Requests", App.Server.TotalRequests.ToString()),
                ("⏱️", "Uptime", $"{App.Server.UptimeSeconds:F1}s")
            );

            dialog.AddSeparator();

            // Server Information
            dialog.AddInfoSection("Server Address", "http://localhost:3000/");

            // Revit Information
            string revitInfo = $"Revit {App.RevitVersion ?? "Unknown"}";
            dialog.AddInfoSection("Revit Version", revitInfo);

            // Document Information
            if (doc != null)
            {
                string docInfo = $"{doc.Title}\n" +
                                $"Status: {(doc.IsModified ? "Modified" : "Not Modified")}\n" +
                                $"Workshared: {(doc.IsWorkshared ? "Yes" : "No")}";
                dialog.AddInfoSection("Active Document", docInfo);
            }
            else
            {
                dialog.AddInfoSection("Active Document", "No document open");
            }

            dialog.AddSeparator();

            // Capabilities
            string capabilities = "✅ Universal Bridge Enabled\n" +
                                 "✅ 233 Available Tools\n" +
                                 "✅ Reflection API (10,000+ methods)\n" +
                                 "✅ Natural Language Support\n" +
                                 "✅ AI-Ready Interface";
            dialog.AddInfoSection("Capabilities", capabilities);

            dialog.SetActionButton("Close");
            dialog.ShowDialog();
        }

        private void ShowErrorDialog()
        {
            var dialog = new ModernDialog();
            dialog.SetTitle("Error", "Server Not Initialized");

            dialog.AddStatusCard(
                "❌",
                "Error",
                "Server not initialized properly. Please restart Revit.",
                new SolidColorBrush(Color.FromRgb(244, 67, 54))
            );

            dialog.SetActionButton("OK");
            dialog.ShowDialog();
        }
    }
}
