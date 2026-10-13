using System;
using System.IO;
using RevitBridge.Bridge;

static class Program
{
    static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    static int Main(string[] args)
    {
        var originalDirectory = Directory.GetCurrentDirectory();
        var testDirectory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "unrelated-working-directory");
        Directory.CreateDirectory(testDirectory);
        File.WriteAllText(Path.Combine(testDirectory, "json.py"), "raise RuntimeError('wrong json library')");
        Directory.SetCurrentDirectory(testDirectory);
        try
        {
            var engine = PythonEngineFactory.Create();
            try
            {
                var scope = engine.CreateScope();
                engine.Execute(
                    "import json, time, collections, os\n" +
                    "assert json.loads(json.dumps({'count': 6}))['count'] == 6\n" +
                    "assert time.time() > 0\n" +
                    "assert collections.Counter(['wall', 'wall'])['wall'] == 2\n" +
                    "assert os.path.basename('villa.png') == 'villa.png'\n" +
                    "result = 'stdlib works'\n", scope);
                Check(scope.GetVariable<string>("result") == "stdlib works", "Real library functions failed");
                Check(engine.LanguageVersion.Major == int.Parse(args[0]), "Unexpected Python language major version");
                Check(engine.LanguageVersion.Minor == int.Parse(args[1]), "Unexpected Python language minor version");
                var description = PythonEngineFactory.Describe(engine);
                var descriptionType = description.GetType();
                Check((bool)descriptionType.GetProperty("standard_library_available").GetValue(description, null),
                    "Verified standard library should be reported available");
                Check((string)descriptionType.GetProperty("version").GetValue(description, null) == engine.LanguageVersion.ToString(),
                    "Reported runtime version must match the actual engine");
                Console.WriteLine("PASS: real IronPython " + engine.LanguageVersion +
                    " imports json/time/collections/os from bundled dependencies, executes their functions, and ignores working-directory json.py.");
            }
            finally
            {
                engine.Runtime.Shutdown();
            }

            var libraryPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Lib");
            var hiddenLibrary = libraryPath + "-missing-test";
            Directory.Move(libraryPath, hiddenLibrary);
            try
            {
                try
                {
                    PythonEngineFactory.Create();
                    throw new Exception("Missing packaged library should fail initialization");
                }
                catch (FileNotFoundException error)
                {
                    Check(error.Message.Contains("Bundled IronPython dependencies are incomplete"), "Packaging error should be actionable");
                }
            }
            finally
            {
                Directory.Move(hiddenLibrary, libraryPath);
            }
            Console.WriteLine("PASS: missing packaged standard library gives an actionable failure.");

            var modulesPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "IronPython.Modules.dll");
            var hiddenModules = modulesPath + "-missing-test";
            File.Move(modulesPath, hiddenModules);
            try
            {
                try
                {
                    PythonEngineFactory.Create();
                    throw new Exception("Missing built-in modules should fail initialization");
                }
                catch (FileNotFoundException error)
                {
                    Check(error.Message.Contains("Bundled IronPython dependencies are incomplete"), "Missing modules error should be actionable");
                }
                File.Copy(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "IronPython.dll"), modulesPath);
                try
                {
                    PythonEngineFactory.Create();
                    throw new Exception("Mismatched built-in module assembly should fail initialization");
                }
                catch (InvalidOperationException error)
                {
                    Check(error.Message.Contains("does not match"), "Mismatched modules error should be actionable");
                }
            }
            finally
            {
                if (File.Exists(modulesPath)) File.Delete(modulesPath);
                File.Move(hiddenModules, modulesPath);
            }
            Console.WriteLine("PASS: missing or mismatched built-in module assembly fails clearly.");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("FAIL: " + error);
            return 1;
        }
        finally
        {
            Directory.SetCurrentDirectory(originalDirectory);
        }
    }
}
