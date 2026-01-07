using System;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

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
                    TaskDialog.Show("RevitMCP", "Bridge Server Started Successfully.");
                }
                else
                {
                    TaskDialog.Show("RevitMCP", "Bridge Server is already running.");
                }
            }
            return Result.Succeeded;
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
                    TaskDialog.Show("RevitMCP", "Bridge Server Stopped.");
                }
                else
                {
                    TaskDialog.Show("RevitMCP", "Bridge Server is already stopped.");
                }
            }
            return Result.Succeeded;
        }
    }

    [Transaction(TransactionMode.Manual)]
    public class CommandStatus : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            if (App.Server == null)
            {
                TaskDialog.Show("RevitMCP Status", "Error: Server not initialized");
                return Result.Failed;
            }

            var doc = commandData.Application.ActiveUIDocument?.Document;
            string docInfo = doc != null
                ? $"{doc.Title} ({(doc.IsModified ? "Modified" : "Not Modified")})"
                : "No document open";

            string statusIcon = App.Server.IsRunning ? "✅" : "🛑";
            string statusText = $@"Server: {statusIcon} {(App.Server.IsRunning ? "Running" : "Stopped")}
Address: http://localhost:3000/
Revit Version: {App.RevitVersion ?? "Unknown"}

Document: {docInfo}

Statistics:
  Active Connections: {App.Server.ActiveConnections}
  Total Requests: {App.Server.TotalRequests}
  Uptime: {App.Server.UptimeSeconds:F1}s

Universal Bridge: ✅ Enabled
Available Tools: 100+
Reflection API: 10,000+ methods";

            var dialog = new TaskDialog("RevitMCP Bridge Status")
            {
                MainInstruction = App.Server.IsRunning ? "Bridge is Running" : "Bridge is Stopped",
                MainContent = statusText,
                CommonButtons = TaskDialogCommonButtons.Close
            };

            dialog.Show();
            return Result.Succeeded;
        }
    }
}
