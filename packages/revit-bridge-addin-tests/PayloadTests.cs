using System;
using System.Collections.Generic;
using System.IO;
using RevitBridge.Bridge;
using Xunit;

namespace RevitBridge.Tests;

public class PayloadPathValidatorTests
{
    private static List<string> Checked(string json)
    {
        var seen = new List<string>();
        PayloadPathValidator.Validate(Json.Parse(json), seen.Add);
        return seen;
    }

    [Theory]
    [InlineData("path")]
    [InlineData("output_path")]
    [InlineData("Path")]
    [InlineData("OUTPUT_PATH")]
    [InlineData("file")]
    [InlineData("filename")]
    [InlineData("template_file")]
    public void String_values_under_path_or_file_names_are_checked(string name)
    {
        Assert.Equal(new[] { "C:\\x\\y.rvt" }, Checked("{\"" + name + "\": \"C:\\\\x\\\\y.rvt\"}"));
    }

    [Fact]
    public void Other_string_values_are_not_checked()
    {
        Assert.Empty(Checked("{\"level\": \"Level 1\", \"name\": \"C:\\\\x\", \"wall_type\": \"Generic\"}"));
    }

    [Fact]
    public void Empty_and_null_and_non_string_values_are_skipped()
    {
        Assert.Empty(Checked("{\"path\": \"\", \"output_path\": null, \"file\": 5, \"file_id\": true}"));
    }

    [Fact]
    public void Nested_objects_and_arrays_of_objects_are_walked()
    {
        var seen = Checked("{\"a\": {\"b\": {\"output_path\": \"one\"}}, \"items\": [{\"file\": \"two\"}, {\"x\": [{\"path\": \"three\"}]}]}");
        Assert.Equal(new[] { "one", "two", "three" }, seen);
    }

    [Fact]
    public void Top_level_array_is_walked()
    {
        Assert.Equal(new[] { "p" }, Checked("[{\"path\": \"p\"}]"));
    }

    [Fact]
    public void Scalar_payloads_are_ignored()
    {
        Assert.Empty(Checked("\"C:\\\\Windows\""));
        Assert.Empty(Checked("42"));
        Assert.Empty(Checked("null"));
    }

    [Fact]
    public void The_check_is_a_substring_match_on_the_name()
    {
        // "profile" contains "file". Harmless (a bare name is not path-like), but it shows what is sent to the check.
        Assert.Equal(new[] { "Default" }, Checked("{\"profile\": \"Default\"}"));
    }

    [Fact]
    public void Known_gap_plain_strings_inside_an_array_are_not_checked_even_under_a_path_name()
    {
        // Characterisation of current behaviour, not a promise: {"paths": ["C:\\elsewhere\\a.rvt"]} is not validated.
        Assert.Empty(Checked("{\"paths\": [\"C:\\\\elsewhere\\\\a.rvt\"], \"files\": [\"D:\\\\b.rvt\"]}"));
    }

    [Fact]
    public void An_error_from_the_check_stops_the_walk_and_reaches_the_caller()
    {
        var calls = 0;
        Assert.Throws<UnauthorizedAccessException>(() =>
            PayloadPathValidator.Validate(Json.Parse("{\"path\": \"a\", \"file\": \"b\"}"), _ =>
            {
                calls++;
                throw new UnauthorizedAccessException("outside");
            }));
        Assert.Equal(1, calls);
    }
}

[Collection(EnvironmentCollection.Name)]
public class WorkspaceMonitorTests
{
    private static WorkspaceMonitor Monitor(string workspace, string? extraAllowed = null)
    {
        using var scope = new EnvScope(
            (WorkspaceDirectory.EnvVar, workspace),
            ("MCP_REVIT_ALLOWED_DIRECTORIES", extraAllowed));
        return new WorkspaceMonitor();
    }

    [Fact]
    public void Files_inside_the_workspace_are_allowed_and_outside_ones_are_refused()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        Assert.True(monitor.IsInWorkspace(Path.Combine(dir.Path, "out", "a.pdf")));
        Assert.True(monitor.IsInWorkspace(dir.Path));
        Assert.False(monitor.IsInWorkspace(Path.Combine(Path.GetTempPath(), "somewhere-else", "a.pdf")));
    }

    [Fact]
    public void A_sibling_folder_with_the_same_prefix_is_not_inside_the_workspace()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        Assert.False(monitor.IsInWorkspace(dir.Path + "-evil" + Path.DirectorySeparatorChar + "a.pdf"));
    }

    [Fact]
    public void Dot_dot_segments_cannot_climb_out()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        Assert.False(monitor.IsInWorkspace(Path.Combine(dir.Path, "..", "escape.txt")));
        Assert.True(monitor.IsInWorkspace(Path.Combine(dir.Path, "sub", "..", "ok.txt")));
    }

    [Fact]
    public void Empty_path_is_refused_but_a_bare_name_is_not_treated_as_a_path()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        Assert.False(monitor.IsInWorkspace(""));
        Assert.True(monitor.IsInWorkspace("Level 1"));
    }

    [Fact]
    public void Extra_allowed_directories_come_from_the_environment()
    {
        using var workspace = new TempDir();
        using var extra = new TempDir();
        var monitor = Monitor(workspace.Path, extra.Path);
        Assert.True(monitor.IsInWorkspace(Path.Combine(extra.Path, "a.rvt")));
    }

    [Fact]
    public void AssertInWorkspace_throws_for_a_path_outside()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        var outside = Path.Combine(Path.GetTempPath(), "somewhere-else", "a.pdf");
        var ex = Assert.Throws<UnauthorizedAccessException>(() => monitor.AssertInWorkspace(outside));
        Assert.Contains(outside, ex.Message);
        monitor.AssertInWorkspace(Path.Combine(dir.Path, "a.pdf"));
    }

    [Fact]
    public void Validator_with_a_real_monitor_refuses_a_nested_outside_path()
    {
        using var dir = new TempDir();
        var monitor = Monitor(dir.Path);
        var outside = Path.Combine(Path.GetTempPath(), "somewhere-else", "a.pdf").Replace("\\", "\\\\");
        var payload = Json.Parse("{\"views\": [{\"export\": {\"output_path\": \"" + outside + "\"}}]}");
        Assert.Throws<UnauthorizedAccessException>(() => PayloadPathValidator.Validate(payload, monitor.AssertInWorkspace));

        var inside = Path.Combine(dir.Path, "a.pdf").Replace("\\", "\\\\");
        PayloadPathValidator.Validate(Json.Parse("{\"output_path\": \"" + inside + "\"}"), monitor.AssertInWorkspace);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Workspace_defaults_to_Documents_AEC_Model_Bridge_when_the_variable_is_unset_or_blank(string? value)
    {
        using var scope = new EnvScope((WorkspaceDirectory.EnvVar, value));
        Assert.Equal(WorkspaceDirectory.Default(), WorkspaceDirectory.Resolve());
        Assert.EndsWith(Path.Combine("Documents", "AEC Model Bridge"), WorkspaceDirectory.Default());
    }

    [Fact]
    public void Workspace_variable_wins_when_set()
    {
        using var scope = new EnvScope((WorkspaceDirectory.EnvVar, "D:\\work"));
        Assert.Equal("D:\\work", WorkspaceDirectory.Resolve());
    }
}

public class PayloadJsonTests
{
    [Fact]
    public void OptionalString_returns_text_or_null()
    {
        var p = Json.Parse("{\"a\": \"hi\", \"b\": \"  \", \"c\": \"\", \"d\": 5, \"e\": null}");
        Assert.Equal("hi", PayloadJson.OptionalString(p, "a"));
        Assert.Null(PayloadJson.OptionalString(p, "b"));
        Assert.Null(PayloadJson.OptionalString(p, "c"));
        Assert.Null(PayloadJson.OptionalString(p, "d"));
        Assert.Null(PayloadJson.OptionalString(p, "e"));
        Assert.Null(PayloadJson.OptionalString(p, "missing"));
    }

    [Fact]
    public void OptionalString_keeps_inner_and_outer_spaces_of_a_real_value()
    {
        Assert.Equal(" x ", PayloadJson.OptionalString(Json.Parse("{\"a\": \" x \"}"), "a"));
    }

    [Fact]
    public void OptionalBool_reads_true_false_and_null()
    {
        var p = Json.Parse("{\"t\": true, \"f\": false, \"n\": null}");
        Assert.True(PayloadJson.OptionalBool(p, "t"));
        Assert.False(PayloadJson.OptionalBool(p, "f"));
        Assert.Null(PayloadJson.OptionalBool(p, "n"));
        Assert.Null(PayloadJson.OptionalBool(p, "missing"));
    }

    [Theory]
    [InlineData("{\"x\": \"true\"}")]
    [InlineData("{\"x\": 1}")]
    [InlineData("{\"x\": []}")]
    public void OptionalBool_rejects_other_types_and_names_the_field(string json)
    {
        var ex = Assert.Throws<ArgumentException>(() => PayloadJson.OptionalBool(Json.Parse(json), "x"));
        Assert.Contains("x must be a boolean", ex.Message);
    }

    [Theory]
    [InlineData("{\"n\": 7}", 7)]
    [InlineData("{\"n\": 0}", 1)]
    [InlineData("{\"n\": 999999}", 100)]
    [InlineData("{\"n\": -4}", 1)]
    [InlineData("{}", 50)]
    [InlineData("{\"n\": \"7\"}", 50)]
    [InlineData("{\"n\": 7.5}", 50)]
    [InlineData("{\"n\": 99999999999}", 50)]
    [InlineData("{\"n\": null}", 50)]
    [InlineData("[1]", 50)]
    public void ClampedInt_clamps_ints_and_falls_back_for_everything_else(string json, int expected)
    {
        Assert.Equal(expected, PayloadJson.ClampedInt(Json.Parse(json), "n", 50, 1, 100));
    }
}
