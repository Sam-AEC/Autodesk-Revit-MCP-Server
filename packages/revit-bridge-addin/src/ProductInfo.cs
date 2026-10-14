using System;
using System.Diagnostics;
using System.Reflection;

namespace RevitBridge
{
    internal static class ProductInfo
    {
        public const string ProductName = "AEC Model Bridge";
        public const string RepositoryUrl = "https://github.com/Sam-AEC/aec-model-bridge";
        public const string DocumentationUrl = RepositoryUrl + "#quick-start";
        public const string IssuesUrl = RepositoryUrl + "/issues";
        public const string LicensingUrl = RepositoryUrl + "/blob/main/LICENSING.md";
        public const string GitHubProfileUrl = "https://github.com/Sam-AEC";
        public const string LinkedInUrl = "https://www.linkedin.com/in/a-sam-mohammad-92790416b";
        public const string MaintainerEmail = "sammohammadwork@gmail.com";
        public const string MaintainerName = "A. Sam Mohammad";
        public const int McpToolCount = 100;

        public static string Version
        {
            get
            {
                var version = Assembly.GetExecutingAssembly().GetName().Version;
                return version == null
                    ? "Unknown"
                    : $"{version.Major}.{version.Minor}.{version.Build}";
            }
        }

        /// <summary>
        /// Identifies the loaded build: informational version, the assembly's module id (changes
        /// whenever the code changes) and the file's write time. Lets a caller tell that the add-in
        /// Revit loaded is older than the repository.
        /// </summary>
        public static object BuildInfo
        {
            get
            {
                var assembly = Assembly.GetExecutingAssembly();
                string? informational = null;
                string? moduleId = null;
                string? builtUtc = null;
                try { informational = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion; } catch { }
                try { moduleId = assembly.ManifestModule.ModuleVersionId.ToString("N"); } catch { }
                try
                {
                    if (!string.IsNullOrEmpty(assembly.Location))
                        builtUtc = System.IO.File.GetLastWriteTimeUtc(assembly.Location).ToString("o");
                }
                catch { }

                return new
                {
                    version = Version,
                    informational_version = informational ?? Version,
                    module_id = moduleId,
                    assembly_file_time_utc = builtUtc
                };
            }
        }

        public static bool TryOpenUrl(string url, out string? error)
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true
                });
                error = null;
                return true;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                return false;
            }
        }
    }
}
