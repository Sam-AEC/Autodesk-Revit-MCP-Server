using Autodesk.Revit.UI;

namespace RevitBridge.Bridge;

public class App : IExternalApplication
{
    private BridgeServer? _server;

    public Result OnStartup(UIControlledApplication application)
    {
        _server = new BridgeServer();
        _server.Start();
        return Result.Succeeded;
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        _server?.Stop();
        return Result.Succeeded;
    }
}
