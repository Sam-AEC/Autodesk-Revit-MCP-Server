using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;

#nullable enable

namespace RevitBridge.Bridge;

/// <summary>Initializes only the IronPython dependencies shipped beside the add-in.</summary>
internal static class PythonEngineFactory
{
    private static string AddinDirectory => Path.GetDirectoryName(typeof(PythonEngineFactory).Assembly.Location)!;
    private static string StandardLibraryPath => Path.Combine(AddinDirectory, "Lib");

    /// <summary>True when the packaged pure-Python standard library (Lib/) sits beside the DLL.</summary>
    internal static bool StandardLibraryAvailable =>
        File.Exists(Path.Combine(StandardLibraryPath, "json", "__init__.py"));

    internal const string MissingLibraryWarning =
        "The Lib folder (IronPython standard library) is missing next to the add-in DLL, so imports such as json, " +
        "collections or os fail. Scripts that only use the Revit API and built-in modules still run. " +
        "Redeploy the whole add-in output folder with scripts/deploy-addin.ps1 (copying only the DLL leaves Lib behind).";

    /// <summary>
    /// Creates the engine. A missing Lib folder does not stop Python: the engine starts without the
    /// standard library and <see cref="Describe"/> says so, so a partial deploy costs the imports
    /// that need Lib, not every script. A missing or mismatched IronPython.Modules.dll still fails,
    /// because built-in modules such as time would silently be absent.
    /// </summary>
    public static ScriptEngine Create()
    {
        var modulesPath = Path.Combine(AddinDirectory, "IronPython.Modules.dll");
        if (!File.Exists(modulesPath))
            throw new FileNotFoundException(
                "Bundled IronPython dependencies are incomplete. Reinstall the matching add-in including IronPython.Modules.dll and Lib.");

        var modulesName = AssemblyName.GetAssemblyName(modulesPath);
        if (modulesName.Name != "IronPython.Modules" ||
            modulesName.Version != typeof(Python).Assembly.GetName().Version)
            throw new InvalidOperationException("Bundled IronPython.Modules.dll does not match the loaded IronPython engine version.");

        // Revit's application base is not the add-in directory. IronPython's
        // name-based load silently omits built-in modules such as time if this
        // assembly is not resolved. Load the shipped assembly before creating it.
        Assembly.LoadFrom(modulesPath);
        var engine = Python.CreateEngine();
        try
        {
            var libraryAvailable = StandardLibraryAvailable;
            if (libraryAvailable)
            {
                var paths = new List<string>(engine.GetSearchPaths());
                paths.Insert(0, StandardLibraryPath);
                engine.SetSearchPaths(paths);
            }
            // Report availability only after both pure-Python and built-in imports work.
            engine.Execute(libraryAvailable ? "import json, time" : "import time");
            return engine;
        }
        catch
        {
            ShutdownQuietly(engine);
            throw;
        }
    }

    /// <summary>Ends the engine's runtime; never throws. Call after every script so no state leaks into the next one.</summary>
    public static void ShutdownQuietly(ScriptEngine? engine)
    {
        if (engine == null) return;
        try { engine.Runtime.Shutdown(); }
        catch { /* a failed shutdown must not hide the script's own result */ }
    }

    public static object Describe(ScriptEngine engine)
    {
        var available = StandardLibraryAvailable;
        return new
        {
            engine = "IronPython",
            version = engine.LanguageVersion.ToString(),
            standard_library_available = available,
            standard_library_path = StandardLibraryPath,
            standard_library_warning = available ? null : MissingLibraryWarning,
            verified_modules = available ? new[] { "json", "time" } : new[] { "time" }
        };
    }
}
