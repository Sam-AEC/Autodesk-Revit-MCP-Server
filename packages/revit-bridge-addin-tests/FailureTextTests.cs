using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using RevitBridge.Bridge;
using Xunit;

namespace RevitBridge.Tests;

public class FailureTextTests
{
    private static BridgeFailureMessage Msg(string severity, string text, long[]? ids = null, long[]? extra = null, string failureId = "f")
        => new()
        {
            Severity = severity,
            Message = text,
            FailureId = failureId,
            ElementIds = (ids ?? Array.Empty<long>()).ToList(),
            AdditionalElementIds = (extra ?? Array.Empty<long>()).ToList()
        };

    // ---- Describe ----

    [Fact]
    public void Describe_names_the_transaction_and_status()
    {
        var text = BridgeFailureText.Describe("AMB: Create Wall", "RolledBack", Array.Empty<BridgeFailureMessage>(), null);
        Assert.StartsWith("Transaction 'AMB: Create Wall' did not commit (status: RolledBack). ", text);
    }

    [Fact]
    public void Describe_lists_each_message_with_severity_and_element_ids()
    {
        var text = BridgeFailureText.Describe("t", "RolledBack", new[]
        {
            Msg("Error", "Walls overlap", new long[] { 10, 11 }),
            Msg("Warning", "Slightly off axis", new long[] { 12 })
        }, null);
        Assert.Contains("Error: Walls overlap (element ids: 10, 11)", text);
        Assert.Contains("Warning: Slightly off axis (element ids: 12)", text);
        Assert.True(text.IndexOf("Walls overlap", StringComparison.Ordinal) < text.IndexOf("Slightly off axis", StringComparison.Ordinal));
    }

    [Fact]
    public void Describe_merges_additional_ids_and_drops_duplicates()
    {
        var text = BridgeFailureText.Describe("t", "RolledBack", new[] { Msg("Error", "x", new long[] { 1, 2 }, new long[] { 2, 3 }) }, null);
        Assert.Contains("(element ids: 1, 2, 3)", text);
    }

    [Fact]
    public void Describe_appends_the_inner_exception_message_last()
    {
        var text = BridgeFailureText.Describe("t", "Pending", new[] { Msg("Error", "x", new long[] { 1 }) }, new InvalidOperationException("commit blew up"));
        Assert.EndsWith("; commit blew up", text);
    }

    [Fact]
    public void Describe_with_only_an_inner_exception_still_reads_cleanly()
    {
        var text = BridgeFailureText.Describe("t", "Started", Array.Empty<BridgeFailureMessage>(), new Exception("only this"));
        Assert.Equal("Transaction 't' did not commit (status: Started). only this", text);
    }

    [Fact]
    public void Describe_without_any_detail_ends_after_the_status()
    {
        Assert.Equal("Transaction 't' did not commit (status: RolledBack). ",
            BridgeFailureText.Describe("t", "RolledBack", Array.Empty<BridgeFailureMessage>(), null));
    }

    // ---- failed ids and warnings ----

    [Fact]
    public void FailedElementIds_skips_warnings_and_none_and_keeps_errors_and_document_corruption()
    {
        var ids = BridgeFailureText.FailedElementIds(new[]
        {
            Msg("Warning", "w", new long[] { 1 }),
            Msg("None", "n", new long[] { 2 }),
            Msg("Error", "e", new long[] { 3 }, new long[] { 4 }),
            Msg("DocumentCorruption", "c", new long[] { 5 })
        });
        Assert.Equal(new long[] { 3, 4, 5 }, ids);
    }

    [Fact]
    public void FailedElementIds_has_no_duplicates_across_messages()
    {
        var ids = BridgeFailureText.FailedElementIds(new[]
        {
            Msg("Error", "a", new long[] { 7, 8 }),
            Msg("Error", "b", new long[] { 8 }, new long[] { 7, 9 })
        });
        Assert.Equal(new long[] { 7, 8, 9 }, ids);
    }

    [Fact]
    public void FailedElementIds_is_empty_when_there_are_only_warnings()
    {
        Assert.Empty(BridgeFailureText.FailedElementIds(new[] { Msg("Warning", "w", new long[] { 1 }) }));
    }

    [Fact]
    public void Warnings_keeps_only_warning_severity_in_order()
    {
        var kept = BridgeFailureText.Warnings(new[] { Msg("Warning", "w1"), Msg("Error", "e"), Msg("Warning", "w2") });
        Assert.Equal(new[] { "w1", "w2" }, kept.Select(m => m.Message));
    }

    // ---- the message as sent to the client ----

    [Fact]
    public void Failure_message_serializes_with_snake_case_names()
    {
        var json = Json.Parse(JsonSerializer.Serialize(Msg("Error", "m", new long[] { 1 }, new long[] { 2 }, "guid-1")));
        Assert.Equal("Error", json.GetProperty("severity").GetString());
        Assert.Equal("m", json.GetProperty("message").GetString());
        Assert.Equal("guid-1", json.GetProperty("failure_id").GetString());
        Assert.Equal(1, json.GetProperty("element_ids")[0].GetInt64());
        Assert.Equal(2, json.GetProperty("additional_element_ids")[0].GetInt64());
    }

    // ---- AppendWarnings ----

    private static JsonElement Append(object result, params BridgeFailureMessage[] messages)
        => Json.Parse(JsonSerializer.Serialize(BridgeTransactionResults.AppendWarnings(result, messages)));

    [Fact]
    public void AppendWarnings_returns_the_same_object_when_there_is_nothing_to_add()
    {
        var result = new { element_id = 5 };
        Assert.Same(result, BridgeTransactionResults.AppendWarnings(result, Array.Empty<BridgeFailureMessage>()));
    }

    [Fact]
    public void AppendWarnings_keeps_the_result_fields_and_adds_warnings_and_all_messages()
    {
        var json = Append(new { element_id = 5, name = "W1" },
            Msg("Warning", "careful"), Msg("Error", "bad", new long[] { 9 }));
        Assert.Equal(5, json.GetProperty("element_id").GetInt32());
        Assert.Equal("W1", json.GetProperty("name").GetString());
        Assert.Equal(1, json.GetProperty("warnings").GetArrayLength());
        Assert.Equal("careful", json.GetProperty("warnings")[0].GetProperty("message").GetString());
        Assert.Equal(2, json.GetProperty("revit_messages").GetArrayLength());
    }

    [Fact]
    public void AppendWarnings_puts_existing_warnings_first()
    {
        var json = Append(new { warnings = new[] { "earlier" } }, Msg("Warning", "later"));
        var warnings = json.GetProperty("warnings");
        Assert.Equal(2, warnings.GetArrayLength());
        Assert.Equal("earlier", warnings[0].GetString());
        Assert.Equal("later", warnings[1].GetProperty("message").GetString());
    }

    [Fact]
    public void AppendWarnings_wraps_a_result_that_is_not_an_object()
    {
        var json = Append("plain text", Msg("Warning", "w"));
        Assert.Equal("plain text", json.GetProperty("result").GetString());
        Assert.Equal(1, json.GetProperty("warnings").GetArrayLength());
    }

    [Fact]
    public void AppendWarnings_ignores_a_warnings_field_that_is_not_an_array()
    {
        var json = Append(new { warnings = "just text" }, Msg("Warning", "w"));
        Assert.Equal(1, json.GetProperty("warnings").GetArrayLength());
    }

    [Fact]
    public void AppendWarnings_with_only_error_messages_reports_an_empty_warnings_list()
    {
        var json = Append(new { ok = true }, Msg("Error", "e", new long[] { 1 }));
        Assert.Equal(0, json.GetProperty("warnings").GetArrayLength());
        Assert.Equal(1, json.GetProperty("revit_messages").GetArrayLength());
    }
}
