using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using RevitBridge.Bridge;
using Xunit;

namespace RevitBridge.Tests;

public class ReadModeRulesTests
{
    private static string[] Find(string script) => ReadModeRules.FindViolations(script).ToArray();

    [Theory]
    [InlineData("t = Transaction(doc, 'x')", "Transaction")]
    [InlineData("from Autodesk.Revit.DB import Transaction", "Transaction")]
    [InlineData("s = SubTransaction(doc)", "SubTransaction")]
    [InlineData("g = TransactionGroup(doc)", "TransactionGroup")]
    [InlineData("doc.Save()", "Save")]
    [InlineData("doc.SaveAs('a.rvt')", "Save")]
    [InlineData("doc . Save (", "Save")]
    [InlineData("doc.SynchronizeWithCentral(a, b)", "SynchronizeWithCentral")]
    [InlineData("uiapp.PostCommand(cid)", "PostCommand")]
    [InlineData("eval('1+1')", "eval")]
    [InlineData("exec('x=1')", "exec")]
    [InlineData("execfile('a.py')", "exec")]
    [InlineData("m = __import__('o' + 's')", "__import__")]
    [InlineData("import os", "os_modules")]
    [InlineData("from subprocess import run", "os_modules")]
    [InlineData("import urllib2", "os_modules")]
    [InlineData("import io", "os_modules")]
    [InlineData("import socket", "os_modules")]
    [InlineData("import ctypes", "os_modules")]
    [InlineData("import tempfile", "os_modules")]
    [InlineData("import System.IO", "System.IO")]
    [InlineData("System.IO.File.Delete(p)", "System.IO")]
    [InlineData("System . Net . WebClient()", "System.IO")]
    [InlineData("System.Reflection.Assembly.Load(x)", "System.IO")]
    [InlineData("Process.Start('calc')", "System.IO")]
    [InlineData("ProcessStartInfo('x')", "System.IO")]
    [InlineData("f = open('a.txt')", "open")]
    [InlineData("f = file ('a.txt')", "open")]
    public void Each_rule_flags_what_it_is_meant_to_flag(string script, string rule)
    {
        Assert.Contains(rule, Find(script));
    }

    [Theory]
    [InlineData("")]
    [InlineData("print(1)")]
    [InlineData("walls = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).ToElements()")]
    [InlineData("x = TransactionStatus.Started")]
    [InlineData("n = len(Transactions)")]
    [InlineData("doc.Saved = 1")]
    [InlineData("doc.save()")]
    [InlineData("reopen(x)")]
    [InlineData("self.open(x)")]
    [InlineData("opened = 1")]
    [InlineData("result = execute(job)")]
    [InlineData("evaluate(x)")]
    [InlineData("import osx")]
    [InlineData("import ioutil")]
    [InlineData("from collections import OrderedDict")]
    [InlineData("Processor(x)")]
    public void Plain_inspection_scripts_pass(string script)
    {
        Assert.Empty(Find(script));
    }

    [Fact]
    public void Several_violations_are_all_reported_in_rule_order()
    {
        var script = "import os\nTransaction(doc)\ndoc.Save()\nopen('x')";
        Assert.Equal(new[] { "Transaction", "Save", "os_modules", "open" }, Find(script));
    }

    [Fact]
    public void Matching_is_case_sensitive_on_the_api_names()
    {
        Assert.Empty(Find("transaction(doc)"));
        Assert.Empty(Find("TRANSACTION"));
    }

    [Fact]
    public void Rule_names_are_unique_and_every_rule_has_a_name()
    {
        var names = ReadModeRules.Rules.Select(r => r.Name).ToArray();
        Assert.Equal(names.Length, names.Distinct().Count());
        Assert.All(names, n => Assert.False(string.IsNullOrWhiteSpace(n)));
    }

    // ---- the C# list and the Python list must not drift ----

    private static readonly Regex PythonRule = new(
        "\\(\\s*\"(?<name>[^\"]+)\"\\s*,\\s*re\\.compile\\(r\"(?<pattern>(?:[^\"\\\\]|\\\\.)*)\"\\)\\s*\\)",
        RegexOptions.CultureInvariant);

    private static string RepoFile(params string[] parts)
    {
        var root = typeof(ReadModeRulesTests).Assembly
            .GetCustomAttributes(typeof(System.Reflection.AssemblyMetadataAttribute), false)
            .Cast<System.Reflection.AssemblyMetadataAttribute>()
            .FirstOrDefault(a => a.Key == "RepoRoot")?.Value;
        Assert.False(string.IsNullOrEmpty(root), "RepoRoot metadata missing from the test assembly");
        Assert.True(Directory.Exists(Path.Combine(root!, "packages", "mcp-server-revit")), "not the repository root: " + root);
        return Path.Combine(new[] { root! }.Concat(parts).ToArray());
    }

    private static (string Name, string Pattern)[] PythonRules()
    {
        var path = RepoFile("packages", "mcp-server-revit", "src", "revit_mcp_server", "security", "read_mode.py");
        var text = File.ReadAllText(path).Replace("\r\n", "\n");
        var start = text.IndexOf("FORBIDDEN_IN_READ_MODE", StringComparison.Ordinal);
        Assert.True(start >= 0, "FORBIDDEN_IN_READ_MODE not found in read_mode.py");
        var end = text.IndexOf("\n)\n", start, StringComparison.Ordinal);
        Assert.True(end > start, "end of FORBIDDEN_IN_READ_MODE not found");
        return PythonRule.Matches(text.Substring(start, end - start))
            .Cast<Match>()
            .Select(m => (m.Groups["name"].Value, m.Groups["pattern"].Value))
            .ToArray();
    }

    [Fact]
    public void Python_list_was_parsed()
    {
        Assert.True(PythonRules().Length >= 12, "expected the Python read-mode list to parse; the file layout may have changed");
    }

    [Fact]
    public void Rule_names_match_the_python_list_in_the_same_order()
    {
        Assert.Equal(PythonRules().Select(r => r.Name), ReadModeRules.Rules.Select(r => r.Name));
    }

    [Fact]
    public void Rule_patterns_match_the_python_list_text_for_text()
    {
        var python = PythonRules();
        Assert.Equal(python.Length, ReadModeRules.Rules.Length);
        for (var i = 0; i < python.Length; i++)
        {
            Assert.Equal(python[i].Name, ReadModeRules.Rules[i].Name);
            Assert.Equal(python[i].Pattern, ReadModeRules.Rules[i].Pattern.ToString());
        }
    }
}
