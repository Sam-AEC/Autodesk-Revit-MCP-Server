using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;

namespace RevitBridge.Bridge;

/// <summary>Initializes only the IronPython dependencies shipped beside the add-in.</summary>
internal static class PythonEngineFactory
{
    private static string AddinDirectory => Path.GetDirectoryName(typeof(PythonEngineFactory).Assembly.Location)!;
    private static string StandardLibraryPath => Path.Combine(AddinDirectory, "Lib");

    public static ScriptEngine Create()
    {
        var modulesPath = Path.Combine(AddinDirectory, "IronPython.Modules.dll");
        if (!File.Exists(modulesPath) || !File.Exists(Path.Combine(StandardLibraryPath, "json", "__init__.py")))
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
            var paths = new List<string>(engine.GetSearchPaths());
            paths.Insert(0, StandardLibraryPath);
            engine.SetSearchPaths(paths);
            // Report availability only after both pure-Python and built-in imports work.
            engine.Execute("import json, time");
            return engine;
        }
        catch
        {
            engine.Runtime.Shutdown();
            throw;
        }
    }

    public static object Describe(ScriptEngine engine) => new
    {
        engine = "IronPython",
        version = engine.LanguageVersion.ToString(),
        standard_library_available = true,
        standard_library_path = StandardLibraryPath,
        verified_modules = new[] { "json", "time" }
    };
}
