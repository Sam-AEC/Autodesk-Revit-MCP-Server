using System;
using System.Collections.Generic;
using System.IO;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;
using RevitBridge;
using RevitBridge.UI;
using Serilog;

namespace RevitBridge.Bridge
{
    public class App : IExternalApplication
    {
        private BridgeServer? _server;
        private CommandQueue? _queue;
        private ExternalEvent? _externalEvent;
        private PanelHubLauncher? _hubLauncher;

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
                handler.Event = _externalEvent;

                _server = new BridgeServer(_queue, _externalEvent);
                Server = _server; // Expose statically
                _server.Start();

                try
                {
                    BridgePanelProvider.Register(application);
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "Bridge started, but the AEC Model Bridge dockable pane could not be registered");
                }

                try
                {
                    CreateModernRibbonInterface(application);
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "Bridge started, but the AEC Model Bridge ribbon could not be created");
                }

                try
                {
                    // Fire-and-forget: checks/launches in the background, never blocks startup.
                    _hubLauncher = new PanelHubLauncher();
                    _hubLauncher.EnsureRunning();
                }
                catch (Exception ex)
                {
                    Log.Error(ex, "Bridge started, but the panel hub could not be launched");
                }

                application.ControlledApplication.DocumentChanged += (sender, args) =>
                {
                    ActiveDocumentName = args.GetDocument()?.Title;
                    DocumentDirtyTracker.HandleDocumentChanged(sender, args);
                };
                application.ViewActivated += (sender, args) =>
                {
                    ActiveDocumentName = args.CurrentActiveView?.Document?.Title;
                    // Do NOT clear dirty tracker here — it must persist until after a
                    // successful revit_extract_snapshot so get_snapshot_delta has a
                    // complete list. Clearing on view activation dropped the entire
                    // delta whenever the user switched views after editing (H3 fix).
                };

                Log.Information("AEC Model Bridge started for Revit {Version}", RevitVersion);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Log.Fatal(ex, "Failed to start AEC Model Bridge");
                _server?.Stop();
                _externalEvent?.Dispose();
                return Result.Failed;
            }
        }

        private void CreateModernRibbonInterface(UIControlledApplication app)
        {
            string tabName = "AEC Bridge";
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
            RibbonPanel workflowPanel = app.CreateRibbonPanel(tabName, "Workflows");
            RibbonPanel toolsPanel = app.CreateRibbonPanel(tabName, "Tools");

            string assemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;

            // Use pre-existing icon files
            string iconPath = Path.Combine(
                Path.GetDirectoryName(assemblyPath) ?? "",
                "Icons"
            );

            string connectIconPath16 = Path.Combine(iconPath, "connect_16.png");
            string connectIconPath32 = Path.Combine(iconPath, "connect_32.png");
            string disconnectIconPath16 = Path.Combine(iconPath, "disconnect_16.png");
            string disconnectIconPath32 = Path.Combine(iconPath, "disconnect_32.png");
            string statusIconPath16 = Path.Combine(iconPath, "status_16.png");
            string statusIconPath32 = Path.Combine(iconPath, "status_32.png");
            string brandIconPath16 = Path.Combine(iconPath, "brand_16.png");
            string brandIconPath32 = Path.Combine(iconPath, "brand_32.png");
            string settingsIconPath16 = Path.Combine(iconPath, "settings_16.png");
            string settingsIconPath32 = Path.Combine(iconPath, "settings_32.png");
            string helpIconPath16 = Path.Combine(iconPath, "help_16.png");
            string helpIconPath32 = Path.Combine(iconPath, "help_32.png");
            string panelIconPath16 = Path.Combine(iconPath, "panel_16.png");
            string panelIconPath32 = Path.Combine(iconPath, "panel_32.png");
            string healthIconPath16 = Path.Combine(iconPath, "healthcheck_16.png");
            string healthIconPath32 = Path.Combine(iconPath, "healthcheck_32.png");
            string pendingIconPath16 = Path.Combine(iconPath, "pending_16.png");
            string pendingIconPath32 = Path.Combine(iconPath, "pending_32.png");
            string reportsIconPath16 = Path.Combine(iconPath, "reports_16.png");
            string reportsIconPath32 = Path.Combine(iconPath, "reports_32.png");

            // Generate theme-adaptive icons (rewritten each session so they never go stale), then retain
            // in-memory fallbacks if file I/O fails. RefreshRibbonIcons re-skins the buttons when Revit's theme changes.
            try
            {
                IconGenerator.GenerateAllIcons(iconPath);
            }
            catch (Exception ex)
            {
                Log.Error(ex, "Failed to dynamically generate ribbon icons");
            }

            BitmapSource connectIcon16 = LoadIcon(connectIconPath16, IconGenerator.CreateConnectIcon, 16);
            BitmapSource connectIcon32 = LoadIcon(connectIconPath32, IconGenerator.CreateConnectIcon, 32);
            BitmapSource disconnectIcon16 = LoadIcon(disconnectIconPath16, IconGenerator.CreateDisconnectIcon, 16);
            BitmapSource disconnectIcon32 = LoadIcon(disconnectIconPath32, IconGenerator.CreateDisconnectIcon, 32);
            BitmapSource statusIcon16 = LoadIcon(statusIconPath16, IconGenerator.CreateStatusIcon, 16);
            BitmapSource statusIcon32 = LoadIcon(statusIconPath32, IconGenerator.CreateStatusIcon, 32);
            BitmapSource brandIcon16 = LoadIcon(brandIconPath16, IconGenerator.CreateBrandIcon, 16);
            BitmapSource brandIcon32 = LoadIcon(brandIconPath32, IconGenerator.CreateBrandIcon, 32);
            BitmapSource settingsIcon16 = LoadIcon(settingsIconPath16, IconGenerator.CreateSettingsIcon, 16);
            BitmapSource settingsIcon32 = LoadIcon(settingsIconPath32, IconGenerator.CreateSettingsIcon, 32);
            BitmapSource helpIcon16 = LoadIcon(helpIconPath16, IconGenerator.CreateHelpIcon, 16);
            BitmapSource helpIcon32 = LoadIcon(helpIconPath32, IconGenerator.CreateHelpIcon, 32);
            BitmapSource panelIcon16 = LoadIcon(panelIconPath16, IconGenerator.CreatePanelIcon, 16);
            BitmapSource panelIcon32 = LoadIcon(panelIconPath32, IconGenerator.CreatePanelIcon, 32);
            BitmapSource healthIcon16 = LoadIcon(healthIconPath16, IconGenerator.CreateHealthIcon, 16);
            BitmapSource healthIcon32 = LoadIcon(healthIconPath32, IconGenerator.CreateHealthIcon, 32);
            BitmapSource pendingIcon16 = LoadIcon(pendingIconPath16, IconGenerator.CreatePendingIcon, 16);
            BitmapSource pendingIcon32 = LoadIcon(pendingIconPath32, IconGenerator.CreatePendingIcon, 32);
            BitmapSource reportsIcon16 = LoadIcon(reportsIconPath16, IconGenerator.CreateReportsIcon, 16);
            BitmapSource reportsIcon32 = LoadIcon(reportsIconPath32, IconGenerator.CreateReportsIcon, 32);

            // === CONNECTION PANEL ===

            // Connect Button
            PushButtonData connectBtnData = new PushButtonData(
                "cmdConnect",
                "Connect",
                assemblyPath,
                "RevitBridge.Bridge.CommandConnect"
            );
            connectBtnData.ToolTip = "Start the MCP Bridge Server";
            connectBtnData.LongDescription = "Starts AEC Model Bridge to enable MCP automation for Revit software.";
            connectBtnData.Image = connectIcon16;
            connectBtnData.LargeImage = connectIcon32;

            // Disconnect Button
            PushButtonData disconnectBtnData = new PushButtonData(
                "cmdDisconnect",
                "Disconnect",
                assemblyPath,
                "RevitBridge.Bridge.CommandDisconnect"
            );
            disconnectBtnData.ToolTip = "Stop the MCP Bridge Server";
            disconnectBtnData.LongDescription = "Stops AEC Model Bridge and closes all active connections.";
            disconnectBtnData.Image = disconnectIcon16;
            disconnectBtnData.LargeImage = disconnectIcon32;

            // Status Button
            PushButtonData statusBtnData = new PushButtonData(
                "cmdStatus",
                "Status",
                assemblyPath,
                "RevitBridge.Bridge.CommandStatus"
            );
            statusBtnData.ToolTip = "View Server Status and Statistics";
            statusBtnData.LongDescription = "Displays detailed information about the Bridge Server including connection status, statistics, and capabilities.";
            statusBtnData.Image = statusIcon16;
            statusBtnData.LargeImage = statusIcon32;

            // Create stacked items for better layout
            Track(connectionPanel.AddItem(connectBtnData), IconGenerator.CreateConnectIcon);
            Track(connectionPanel.AddItem(disconnectBtnData), IconGenerator.CreateDisconnectIcon);
            connectionPanel.AddSeparator();
            Track(connectionPanel.AddItem(statusBtnData), IconGenerator.CreateStatusIcon);

            // === TOOLS PANEL ===

            // Open Panel Button
            PushButtonData panelBtnData = new PushButtonData(
                "cmdOpenPanel",
                "Open Panel",
                assemblyPath,
                "RevitBridge.Bridge.CommandOpenPanel"
            );
            panelBtnData.ToolTip = "Open the AEC Model Bridge panel";
            panelBtnData.LongDescription = "Shows the dockable AEC Model Bridge panel inside Revit.";
            panelBtnData.Image = panelIcon16;
            panelBtnData.LargeImage = panelIcon32;

            PushButtonData healthBtnData = new PushButtonData(
                "cmdRunHealthCheck",
                "Health Check",
                assemblyPath,
                "RevitBridge.Bridge.CommandRunHealthCheck"
            );
            healthBtnData.ToolTip = "Open the panel and start a model health check";
            healthBtnData.LongDescription = "Opens the findings view and requests a QA/QC health check.";
            healthBtnData.Image = healthIcon16;
            healthBtnData.LargeImage = healthIcon32;

            PushButtonData pendingBtnData = new PushButtonData(
                "cmdReviewPendingActions",
                "Pending Actions",
                assemblyPath,
                "RevitBridge.Bridge.CommandReviewPendingActions"
            );
            pendingBtnData.ToolTip = "Review pending ActionPlans";
            pendingBtnData.LongDescription = "Opens the approval queue in the AEC Model Bridge panel.";
            pendingBtnData.Image = pendingIcon16;
            pendingBtnData.LargeImage = pendingIcon32;

            PushButtonData reportsBtnData = new PushButtonData(
                "cmdReports",
                "Reports",
                assemblyPath,
                "RevitBridge.Bridge.CommandOpenReports"
            );
            reportsBtnData.ToolTip = "Open report tools";
            reportsBtnData.LongDescription = "Opens report export controls in the AEC Model Bridge panel.";
            reportsBtnData.Image = reportsIcon16;
            reportsBtnData.LargeImage = reportsIcon32;

            // Settings Button (future)
            PushButtonData settingsBtnData = new PushButtonData(
                "cmdSettings",
                "Config",
                assemblyPath,
                "RevitBridge.Bridge.CommandSettings"
            );
            settingsBtnData.ToolTip = "View Bridge Configuration";
            settingsBtnData.LongDescription = "View the local server address, runtime behavior, configuration path, and log path.";
            settingsBtnData.Image = settingsIcon16;
            settingsBtnData.LargeImage = settingsIcon32;
            settingsBtnData.AvailabilityClassName = "RevitBridge.Bridge.CommandAvailability";

            // Help Button
            PushButtonData helpBtnData = new PushButtonData(
                "cmdHelp",
                "Help",
                assemblyPath,
                "RevitBridge.Bridge.CommandHelp"
            );
            helpBtnData.ToolTip = "View Documentation";
            helpBtnData.LongDescription = "Open the AEC Model Bridge documentation and user guide.";
            helpBtnData.Image = helpIcon16;
            helpBtnData.LargeImage = helpIcon32;

            // About Button
            PushButtonData aboutBtnData = new PushButtonData(
                "cmdAbout",
                "About",
                assemblyPath,
                "RevitBridge.Bridge.CommandAbout"
            );
            aboutBtnData.ToolTip = "About AEC Model Bridge";
            aboutBtnData.LongDescription = "View the installed version, maintainer, documentation, and support links.";
            aboutBtnData.Image = brandIcon16;
            aboutBtnData.LargeImage = brandIcon32;

            // Every button: brand tooltip image, F1 opens the docs.
            foreach (var data in new[]
            {
                connectBtnData, disconnectBtnData, statusBtnData, panelBtnData, healthBtnData,
                pendingBtnData, reportsBtnData, settingsBtnData, helpBtnData, aboutBtnData
            })
            {
                data.ToolTipImage = brandIcon32;
                data.SetContextualHelp(new ContextualHelp(ContextualHelpType.Url, ProductInfo.DocumentationUrl));
            }

            // Workflows: one large primary action, the secondary ones stacked at 16 px (Revit's own pattern).
            Track(workflowPanel.AddItem(panelBtnData), IconGenerator.CreatePanelIcon);
            var workflowStack = workflowPanel.AddStackedItems(healthBtnData, pendingBtnData, reportsBtnData);
            Track(workflowStack[0], IconGenerator.CreateHealthIcon);
            Track(workflowStack[1], IconGenerator.CreatePendingIcon);
            Track(workflowStack[2], IconGenerator.CreateReportsIcon);

            var toolsStack = toolsPanel.AddStackedItems(settingsBtnData, helpBtnData, aboutBtnData);
            Track(toolsStack[0], IconGenerator.CreateSettingsIcon);
            Track(toolsStack[1], IconGenerator.CreateHelpIcon);
            Track(toolsStack[2], IconGenerator.CreateBrandIcon);

            Log.Information("Modern ribbon interface created with icons");
        }

        private static readonly List<(PushButton Button, Func<int, BitmapSource> Factory)> ThemedButtons =
            new List<(PushButton, Func<int, BitmapSource>)>();

        private static void Track(RibbonItem? item, Func<int, BitmapSource> factory)
        {
            if (item is PushButton button)
            {
                ThemedButtons.Add((button, factory));
            }
        }

        /// <summary>Redraws every ribbon icon for the current Revit theme (called from ThemeChanged).</summary>
        internal static void RefreshRibbonIcons()
        {
            foreach (var (button, factory) in ThemedButtons)
            {
                try
                {
                    button.Image = factory(16);
                    button.LargeImage = factory(32);
                }
                catch (Exception ex)
                {
                    Log.Debug(ex, "Could not refresh ribbon icon for {Button}", button.Name);
                }
            }
        }

        private static BitmapSource LoadIcon(
            string path,
            Func<int, BitmapSource> fallbackFactory,
            int size)
        {
            if (!File.Exists(path))
            {
                Log.Debug("Icon not found at {IconPath}; using generated fallback", path);
                return fallbackFactory(size);
            }

            var icon = new BitmapImage();
            icon.BeginInit();
            icon.CacheOption = BitmapCacheOption.OnLoad;
            icon.UriSource = new Uri(path, UriKind.Absolute);
            icon.EndInit();
            icon.Freeze();
            return icon;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            try
            {
                _hubLauncher?.StopIfLaunched();
                _server?.Stop();
                _externalEvent?.Dispose();
                Log.Information("AEC Model Bridge stopped");
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
                "AECModelBridge", "Logs", "bridge.jsonl"
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
