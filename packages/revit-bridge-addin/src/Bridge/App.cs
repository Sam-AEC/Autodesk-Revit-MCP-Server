using System;
using System.IO;
using Autodesk.Revit.UI;
using RevitBridge.UI;
using Serilog;

namespace RevitBridge.Bridge
{
    public class App : IExternalApplication
    {
        private BridgeServer? _server;
        private CommandQueue? _queue;
        private ExternalEvent? _externalEvent;

        public static string? RevitVersion { get; private set; }
        public static string? ActiveDocumentName { get; private set; }
        public static BridgeServer? Server { get; private set; }

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                InitializeLogging();

                RevitVersion = application.ControlledApplication.VersionNumber;

                _queue = new CommandQueue();
                var handler = new RevitCommandExecutor(_queue);
                _externalEvent = ExternalEvent.Create(handler);

                _server = new BridgeServer(_queue, _externalEvent);
                Server = _server; // Expose statically
                _server.Start();

                // Create Modern Ribbon UI with Icons
                CreateModernRibbonInterface(application);

                application.ControlledApplication.DocumentChanged += (sender, args) =>
                {
                    ActiveDocumentName = args.GetDocument()?.Title;
                };

                Log.Information("RevitMCP Bridge started for Revit {Version}", RevitVersion);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Log.Fatal(ex, "Failed to start RevitMCP Bridge");
                return Result.Failed;
            }
        }

        private void CreateModernRibbonInterface(UIControlledApplication app)
        {
            string tabName = "RevitMCP";
            try
            {
                app.CreateRibbonTab(tabName);
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                // Tab might already exist
            }

            // Create panels
            RibbonPanel connectionPanel = app.CreateRibbonPanel(tabName, "Connection");
            RibbonPanel toolsPanel = app.CreateRibbonPanel(tabName, "Tools");

            string assemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;

            // Generate icons directory
            string iconPath = Path.Combine(
                Path.GetDirectoryName(assemblyPath) ?? "",
                "Icons"
            );
            Directory.CreateDirectory(iconPath);

            // Generate and save icons
            var connectIcon = IconGenerator.CreateConnectIcon(32);
            var disconnectIcon = IconGenerator.CreateDisconnectIcon(32);
            var statusIcon = IconGenerator.CreateStatusIcon(32);
            var brandIcon = IconGenerator.CreateBrandIcon(32);
            var settingsIcon = IconGenerator.CreateSettingsIcon(32);

            string connectIconPath = Path.Combine(iconPath, "connect.png");
            string disconnectIconPath = Path.Combine(iconPath, "disconnect.png");
            string statusIconPath = Path.Combine(iconPath, "status.png");
            string brandIconPath = Path.Combine(iconPath, "brand.png");
            string settingsIconPath = Path.Combine(iconPath, "settings.png");

            IconGenerator.SaveIcon(connectIcon, connectIconPath);
            IconGenerator.SaveIcon(disconnectIcon, disconnectIconPath);
            IconGenerator.SaveIcon(statusIcon, statusIconPath);
            IconGenerator.SaveIcon(brandIcon, brandIconPath);
            IconGenerator.SaveIcon(settingsIcon, settingsIconPath);

            // === CONNECTION PANEL ===

            // Connect Button
            PushButtonData connectBtnData = new PushButtonData(
                "cmdConnect",
                "Connect",
                assemblyPath,
                "RevitBridge.Bridge.CommandConnect"
            );
            connectBtnData.ToolTip = "Start the MCP Bridge Server";
            connectBtnData.LongDescription = "Starts the RevitMCP Bridge Server to enable AI-powered automation and natural language control of Revit.";
            connectBtnData.Image = new System.Windows.Media.Imaging.BitmapImage(new Uri(connectIconPath));
            connectBtnData.LargeImage = new System.Windows.Media.Imaging.BitmapImage(new Uri(connectIconPath));
            connectBtnData.ToolTipImage = new System.Windows.Media.Imaging.BitmapImage(new Uri(brandIconPath));

            // Disconnect Button
            PushButtonData disconnectBtnData = new PushButtonData(
                "cmdDisconnect",
                "Disconnect",
                assemblyPath,
                "RevitBridge.Bridge.CommandDisconnect"
            );
            disconnectBtnData.ToolTip = "Stop the MCP Bridge Server";
            disconnectBtnData.LongDescription = "Stops the RevitMCP Bridge Server and closes all active connections.";
            disconnectBtnData.Image = new System.Windows.Media.Imaging.BitmapImage(new Uri(disconnectIconPath));
            disconnectBtnData.LargeImage = new System.Windows.Media.Imaging.BitmapImage(new Uri(disconnectIconPath));

            // Status Button
            PushButtonData statusBtnData = new PushButtonData(
                "cmdStatus",
                "Status",
                assemblyPath,
                "RevitBridge.Bridge.CommandStatus"
            );
            statusBtnData.ToolTip = "View Server Status and Statistics";
            statusBtnData.LongDescription = "Displays detailed information about the Bridge Server including connection status, statistics, and capabilities.";
            statusBtnData.Image = new System.Windows.Media.Imaging.BitmapImage(new Uri(statusIconPath));
            statusBtnData.LargeImage = new System.Windows.Media.Imaging.BitmapImage(new Uri(statusIconPath));

            // Create stacked items for better layout
            connectionPanel.AddItem(connectBtnData);
            connectionPanel.AddItem(disconnectBtnData);
            connectionPanel.AddSeparator();
            connectionPanel.AddItem(statusBtnData);

            // === TOOLS PANEL ===

            // Settings Button (future)
            PushButtonData settingsBtnData = new PushButtonData(
                "cmdSettings",
                "Settings",
                assemblyPath,
                "RevitBridge.Bridge.CommandSettings"
            );
            settingsBtnData.ToolTip = "Configure Bridge Settings";
            settingsBtnData.LongDescription = "Configure server settings, port, logging, and other options.";
            settingsBtnData.Image = new System.Windows.Media.Imaging.BitmapImage(new Uri(settingsIconPath));
            settingsBtnData.LargeImage = new System.Windows.Media.Imaging.BitmapImage(new Uri(settingsIconPath));
            settingsBtnData.AvailabilityClassName = "RevitBridge.Bridge.CommandAvailability";

            // Help Button
            PushButtonData helpBtnData = new PushButtonData(
                "cmdHelp",
                "Help",
                assemblyPath,
                "RevitBridge.Bridge.CommandHelp"
            );
            helpBtnData.ToolTip = "View Documentation";
            helpBtnData.LongDescription = "Open the RevitMCP Bridge documentation and user guide.";

            toolsPanel.AddItem(settingsBtnData);
            toolsPanel.AddItem(helpBtnData);

            // Add panel title text
            TextBoxData textBoxData = new TextBoxData("txtInfo");
            textBoxData.ToolTip = "AI-Powered Revit Automation";

            Log.Information("Modern ribbon interface created with icons");
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            try
            {
                _server?.Stop();
                _externalEvent?.Dispose();
                Log.Information("RevitMCP Bridge stopped");
                Log.CloseAndFlush();
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Log.Error(ex, "Error during shutdown");
                return Result.Failed;
            }
        }

        private void InitializeLogging()
        {
            var logPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "RevitMCP", "Logs", "bridge.jsonl"
            );

            Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);

            Log.Logger = new LoggerConfiguration()
                .WriteTo.File(
                    logPath,
                    rollingInterval: RollingInterval.Day,
                    outputTemplate: "{Timestamp:yyyy-MM-dd HH:mm:ss.fff zzz} [{Level:u3}] {Message:lj}{NewLine}{Exception}"
                )
                .CreateLogger();
        }
    }

    /// <summary>
    /// Command availability controller (for future use)
    /// </summary>
    public class CommandAvailability : IExternalCommandAvailability
    {
        public bool IsCommandAvailable(UIApplication applicationData, Autodesk.Revit.DB.CategorySet selectedCategories)
        {
            // For now, always available
            return true;
        }
    }
}
