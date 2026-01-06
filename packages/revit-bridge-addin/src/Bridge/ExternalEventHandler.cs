using Autodesk.Revit.UI;

namespace RevitBridge.Bridge;

public class ExternalEventHandler : IExternalEventHandler
{
    public void Execute(UIApplication app)
    {
        // Placeholder executor; future iterations will queue BridgeCommandFactory requests
    }

    public string GetName() => "Revit MCP Bridge Executor";
}
