using System;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Bridge;

public static partial class BridgeCommandFactory
{
    // Read-only snapshot of what this Revit session is: which build of the add-in is loaded, which
    // document and view are active, and how busy the bridge is. The approval mode is held by the MCP
    // server, not the add-in, so it is added on that side.
    [BridgeCommand("revit.get_context", IsMutating = false)]
    private static object ExecuteGetContext(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;

        object? document = null;
        if (doc != null)
        {
            string? centralPath = null;
            if (doc.IsWorkshared)
            {
                try
                {
                    centralPath = ModelPathUtils.ConvertModelPathToUserVisiblePath(doc.GetWorksharingCentralModelPath());
                }
                catch (Exception)
                {
                    // Detached or not yet saved: no central path to report.
                }
            }

            var view = doc.ActiveView;
            document = new
            {
                title = doc.Title,
                path = string.IsNullOrEmpty(doc.PathName) ? "unsaved" : doc.PathName,
                guid = doc.CreationGUID.ToString(),
                is_family = doc.IsFamilyDocument,
                is_modified = doc.IsModified,
                is_workshared = doc.IsWorkshared,
                central_path = centralPath,
                active_view = view == null
                    ? null
                    : new { id = view.Id.Value, name = view.Name, type = view.ViewType.ToString() }
            };
        }

        var queue = App.Server?.Queue;
        return new
        {
            addin = ProductInfo.BuildInfo,
            revit = new
            {
                version = app.Application.VersionNumber,
                name = app.Application.VersionName,
                build = app.Application.VersionBuild,
                username = app.Application.Username
            },
            document,
            queue = new
            {
                // Requests waiting behind this one. This command is itself the request Revit is
                // running, so a long-running job shows up in /health, which is not queued.
                depth = queue?.Count ?? 0,
                retained_results = queue?.FinishedCount ?? 0,
                result_ttl_seconds = (int)(queue?.ResultTtl.TotalSeconds ?? 0)
            }
        };
    }
}
