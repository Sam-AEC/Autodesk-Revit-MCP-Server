using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace RevitBridge.Bridge;

/// <summary>
/// The read-mode text check, kept free of Revit types so it can be tested without Revit
/// (packages/revit-bridge-addin-tests). Used by <see cref="PythonScriptRunner"/>.
/// </summary>
internal static class ReadModeRules
{
    // Keep in step with revit_mcp_server/security/read_mode.py (a test compares the rule names).
    internal static readonly (string Name, Regex Pattern)[] Rules =
    {
        ("Transaction", new Regex(@"\bTransaction\b", RegexOptions.CultureInvariant)),
        ("SubTransaction", new Regex(@"\bSubTransaction\b", RegexOptions.CultureInvariant)),
        ("TransactionGroup", new Regex(@"\bTransactionGroup\b", RegexOptions.CultureInvariant)),
        ("Save", new Regex(@"\.\s*Save(?:As)?\s*\(", RegexOptions.CultureInvariant)),
        ("SynchronizeWithCentral", new Regex(@"\bSynchronizeWithCentral\b", RegexOptions.CultureInvariant)),
        ("PostCommand", new Regex(@"\bPostCommand\b", RegexOptions.CultureInvariant)),
        ("eval", new Regex(@"\beval\b", RegexOptions.CultureInvariant)),
        ("exec", new Regex(@"\bexec(?:file)?\b", RegexOptions.CultureInvariant)),
        ("__import__", new Regex(@"\b__import__\b", RegexOptions.CultureInvariant)),
        ("os_modules", new Regex(@"\b(?:import|from)\s+(?:os|subprocess|shutil|socket|ctypes|urllib\w*|http|ftplib|smtplib|pickle|marshal|webbrowser|tempfile|glob|io)\b", RegexOptions.CultureInvariant)),
        ("System.IO", new Regex(@"\bSystem\s*\.\s*(?:IO|Net|Reflection)\b|\bProcess(?:StartInfo)?\s*[.(]", RegexOptions.CultureInvariant)),
        ("open", new Regex(@"(?<![\w.])(?:open|file)\s*\(", RegexOptions.CultureInvariant)),
    };

    internal static List<string> FindViolations(string script)
    {
        return Rules.Where(rule => rule.Pattern.IsMatch(script)).Select(rule => rule.Name).ToList();
    }
}
