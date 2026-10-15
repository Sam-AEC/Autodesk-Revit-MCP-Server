using System;
using System.Text.Json;
using System.Threading.Tasks;
using RevitBridge.Bridge;
using Xunit;

namespace RevitBridge.Tests;

[Collection(EnvironmentCollection.Name)]
public class CommandQueueTests
{
    private static readonly TimeSpan Ttl = TimeSpan.FromSeconds(900);
    private static readonly TimeSpan Abandon = TimeSpan.FromSeconds(120);

    private static CommandQueue Create(FakeClock clock, int maxEntries = 500, long maxBytes = 64L * 1024 * 1024, TimeSpan? ttl = null, TimeSpan? abandon = null)
        => new(ttl ?? Ttl, abandon ?? Abandon, maxEntries, maxBytes, clock.Read);

    private static CommandRequest Request(string id, string tool = "revit.health")
        => new() { RequestId = id, Tool = tool, Payload = Json.Parse("{}") };

    private static CommandResponse Ok(string tool = "revit.health", object? result = null)
        => new() { Status = "ok", Tool = tool, Result = result ?? new { n = 1 } };

    // ---- request id handling ----

    [Fact]
    public void Enqueue_new_id_is_queued_and_dequeued_once()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        Assert.Equal(1, q.Count);
        Assert.True(q.TryDequeue(out var req));
        Assert.Equal("a", req!.RequestId);
        Assert.False(q.TryDequeue(out var none));
        Assert.Null(none);
    }

    [Fact]
    public void Retry_with_same_id_while_queued_does_not_queue_a_second_copy()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.Enqueue(Request("a"));
        q.Enqueue(Request("a"));
        Assert.Equal(1, q.Count);
    }

    [Fact]
    public void Retry_with_same_id_while_running_does_not_queue_again()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.MarkRunning("a");
        q.Enqueue(Request("a"));
        Assert.Equal(0, q.Count);
        Assert.Equal("running", q.GetSnapshot("a")!.State);
    }

    [Fact]
    public void Retry_with_same_id_after_finish_is_answered_from_the_stored_result_and_not_rerun()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.MarkRunning("a");
        q.Complete("a", Ok());
        var first = q.GetSnapshot("a")!.ResponseJson;

        q.Enqueue(Request("a"));

        Assert.Equal(0, q.Count);
        Assert.Equal(first, q.GetSnapshot("a")!.ResponseJson);
        Assert.Equal("done", q.GetSnapshot("a")!.State);
    }

    [Fact]
    public void Request_ids_are_case_sensitive()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("abc"));
        q.Enqueue(Request("ABC"));
        Assert.Equal(2, q.Count);
    }

    [Fact]
    public void Requests_are_dequeued_in_order()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("1"));
        q.Enqueue(Request("2"));
        q.Enqueue(Request("3"));
        foreach (var expected in new[] { "1", "2", "3" })
        {
            Assert.True(q.TryDequeue(out var r));
            Assert.Equal(expected, r!.RequestId);
        }
    }

    [Fact]
    public void Unknown_id_has_no_snapshot_and_is_not_wanted()
    {
        var q = Create(new FakeClock());
        Assert.Null(q.GetSnapshot("nope"));
        Assert.False(q.IsWanted("nope"));
    }

    // ---- states ----

    [Fact]
    public void State_goes_queued_running_done()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a", "revit.create_wall"));
        Assert.Equal("queued", q.GetSnapshot("a")!.State);
        Assert.Null(q.GetRunning());

        q.TryDequeue(out _);
        clock.Advance(TimeSpan.FromSeconds(2));
        q.MarkRunning("a");
        var running = q.GetRunning();
        Assert.NotNull(running);
        Assert.Equal("a", running!.RequestId);
        Assert.Equal("revit.create_wall", running.Tool);

        clock.Advance(TimeSpan.FromSeconds(3));
        q.Complete("a", Ok("revit.create_wall"));
        var done = q.GetSnapshot("a")!;
        Assert.Equal("done", done.State);
        Assert.True(done.IsFinished);
        Assert.NotNull(done.ResponseJson);
        Assert.Null(q.GetRunning());
    }

    [Fact]
    public void Error_response_marks_the_request_failed()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", new CommandResponse { Status = "error", Tool = "t", Message = "boom" });
        var snap = q.GetSnapshot("a")!;
        Assert.Equal("failed", snap.State);
        Assert.True(snap.IsFinished);
        var json = Json.Parse(snap.ResponseJson!);
        Assert.Equal("error", json.GetProperty("Status").GetString());
        Assert.Equal("boom", json.GetProperty("Message").GetString());
    }

    [Fact]
    public void Elapsed_time_runs_from_enqueue_while_queued_from_start_while_running_and_is_the_total_once_finished()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        clock.Advance(TimeSpan.FromSeconds(4));
        Assert.Equal(4000, q.GetSnapshot("a")!.ElapsedMs);

        q.TryDequeue(out _);
        q.MarkRunning("a");
        clock.Advance(TimeSpan.FromSeconds(3));
        Assert.Equal(3000, q.GetSnapshot("a")!.ElapsedMs);

        q.Complete("a", Ok());
        var atFinish = q.GetSnapshot("a")!.ElapsedMs;
        clock.Advance(TimeSpan.FromSeconds(60));
        Assert.Equal(atFinish, q.GetSnapshot("a")!.ElapsedMs);
        Assert.Equal(7000, atFinish); // enqueue to finish
    }

    [Fact]
    public void MarkRunning_on_a_finished_request_does_not_reopen_it()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        q.MarkRunning("a");
        Assert.Equal("done", q.GetSnapshot("a")!.State);
    }

    [Fact]
    public void Completing_twice_keeps_the_first_result()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok(result: new { v = "first" }));
        q.Complete("a", new CommandResponse { Status = "error", Tool = "t", Message = "second" });
        var snap = q.GetSnapshot("a")!;
        Assert.Equal("done", snap.State);
        Assert.Contains("first", snap.ResponseJson);
        Assert.Equal(1, q.FinishedCount);
    }

    [Fact]
    public void Completing_an_unknown_id_is_ignored()
    {
        var q = Create(new FakeClock());
        q.Complete("ghost", Ok());
        Assert.Null(q.GetSnapshot("ghost"));
        Assert.Equal(0, q.FinishedCount);
    }

    [Fact]
    public void Result_that_cannot_be_serialized_is_stored_as_an_error_response()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", new CommandResponse { Status = "ok", Tool = "t", Result = new Unserializable() });
        var snap = q.GetSnapshot("a")!;
        Assert.True(snap.IsFinished);
        var json = Json.Parse(snap.ResponseJson!);
        Assert.Equal("error", json.GetProperty("Status").GetString());
        Assert.Contains("could not be serialized", json.GetProperty("Message").GetString());
        Assert.Equal("t", json.GetProperty("Tool").GetString());
    }

    private sealed class Unserializable
    {
        public string Value => throw new InvalidOperationException("no");
    }

    // ---- abandoned requests ----

    [Fact]
    public void Queued_request_is_wanted_until_nobody_has_asked_about_it_for_AbandonAfter()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        clock.Advance(Abandon);
        Assert.True(q.IsWanted("a"));
        clock.Advance(TimeSpan.FromSeconds(1));
        Assert.False(q.IsWanted("a"));
    }

    [Fact]
    public void Asking_about_a_request_keeps_it_wanted()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        clock.Advance(TimeSpan.FromSeconds(100));
        q.GetSnapshot("a");
        clock.Advance(TimeSpan.FromSeconds(100));
        Assert.True(q.IsWanted("a"));
    }

    [Fact]
    public void A_retry_with_the_same_id_keeps_the_request_wanted()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        clock.Advance(TimeSpan.FromSeconds(100));
        q.Enqueue(Request("a"));
        clock.Advance(TimeSpan.FromSeconds(100));
        Assert.True(q.IsWanted("a"));
    }

    [Fact]
    public void A_finished_request_is_not_wanted()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        Assert.False(q.IsWanted("a"));
    }

    // ---- result cache: TTL and bounds ----

    [Fact]
    public void Finished_result_stays_retrievable_for_the_TTL_then_expires()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok());

        clock.Advance(Ttl);
        q.Enqueue(Request("other1"));
        Assert.NotNull(q.GetSnapshot("a"));

        clock.Advance(TimeSpan.FromSeconds(1));
        q.Enqueue(Request("other2"));
        Assert.Null(q.GetSnapshot("a"));
        Assert.Equal(0, q.FinishedCount);
    }

    [Fact]
    public void Expired_result_is_also_swept_when_another_request_completes()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        q.Enqueue(Request("b"));
        q.TryDequeue(out _);
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        clock.Advance(Ttl + TimeSpan.FromSeconds(1));
        q.Complete("b", Ok());
        Assert.Null(q.GetSnapshot("a"));
        Assert.NotNull(q.GetSnapshot("b"));
    }

    [Fact]
    public void Expired_id_can_be_submitted_again_and_runs_again()
    {
        var clock = new FakeClock();
        var q = Create(clock);
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        clock.Advance(Ttl + TimeSpan.FromSeconds(1));

        q.Enqueue(Request("a"));

        Assert.Equal(1, q.Count);
        Assert.Equal("queued", q.GetSnapshot("a")!.State);
    }

    [Fact]
    public void Queued_and_running_requests_never_expire_by_TTL()
    {
        var clock = new FakeClock();
        var q = Create(clock, ttl: TimeSpan.FromSeconds(30));
        q.Enqueue(Request("running"));
        q.Enqueue(Request("queued"));
        q.TryDequeue(out _);
        q.MarkRunning("running");
        clock.Advance(TimeSpan.FromHours(2));
        q.Enqueue(Request("trigger-sweep"));
        Assert.Equal("running", q.GetSnapshot("running")!.State);
        Assert.Equal("queued", q.GetSnapshot("queued")!.State);
    }

    [Fact]
    public void Finished_results_are_capped_by_count_and_the_oldest_go_first()
    {
        var clock = new FakeClock();
        var q = Create(clock, maxEntries: 2);
        foreach (var id in new[] { "a", "b", "c" })
        {
            q.Enqueue(Request(id));
            q.TryDequeue(out _);
            q.Complete(id, Ok());
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        Assert.Null(q.GetSnapshot("a"));
        Assert.NotNull(q.GetSnapshot("b"));
        Assert.NotNull(q.GetSnapshot("c"));
        Assert.Equal(2, q.FinishedCount);
    }

    [Fact]
    public void Finished_results_are_capped_by_bytes_and_the_oldest_go_first()
    {
        var clock = new FakeClock();
        var big = new string('x', 2000);
        var q = Create(clock, maxBytes: 3000);
        foreach (var id in new[] { "a", "b" })
        {
            q.Enqueue(Request(id));
            q.TryDequeue(out _);
            q.Complete(id, Ok(result: new { big }));
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        Assert.Null(q.GetSnapshot("a"));
        Assert.NotNull(q.GetSnapshot("b"));
    }

    // ---- waiting ----

    [Fact]
    public async Task WaitForResponse_for_an_unknown_id_returns_null()
    {
        var q = Create(new FakeClock());
        Assert.Null(await q.WaitForResponse("nope", 10));
    }

    [Fact]
    public async Task WaitForResponse_times_out_with_the_request_still_pending_and_in_place()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        var snap = await q.WaitForResponse("a", 20);
        Assert.NotNull(snap);
        Assert.False(snap!.IsFinished);
        Assert.Equal("queued", snap.State);
        Assert.NotNull(q.GetSnapshot("a"));
    }

    [Fact]
    public async Task WaitForResponse_returns_as_soon_as_the_request_completes()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        var waiting = q.WaitForResponse("a", 10000);
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        var snap = await waiting;
        Assert.True(snap!.IsFinished);
        Assert.Equal("done", snap.State);
    }

    [Fact]
    public async Task WaitForResponse_on_a_finished_request_returns_immediately()
    {
        var q = Create(new FakeClock());
        q.Enqueue(Request("a"));
        q.TryDequeue(out _);
        q.Complete("a", Ok());
        var snap = await q.WaitForResponse("a", 10000);
        Assert.True(snap!.IsFinished);
    }

    // ---- limits from the environment (public constructor) ----

    [Theory]
    [InlineData(null, 900)]
    [InlineData("abc", 900)]
    [InlineData("", 900)]
    [InlineData("600", 600)]
    [InlineData("5", 30)]
    [InlineData("99999999", 86400)]
    public void ResultTtl_comes_from_the_environment_clamped_with_a_fifteen_minute_default(string? env, int expectedSeconds)
    {
        using var scope = new EnvScope(("AEC_BRIDGE_RESULT_TTL_SECONDS", env));
        Assert.Equal(TimeSpan.FromSeconds(expectedSeconds), new CommandQueue().ResultTtl);
    }

    [Fact]
    public void Other_limits_have_defaults_and_clamps()
    {
        using var scope = new EnvScope(
            ("AEC_BRIDGE_ABANDON_SECONDS", null),
            ("AEC_BRIDGE_RESULT_MAX_ENTRIES", "1"),
            ("AEC_BRIDGE_RESULT_MAX_MB", "100000"));
        var q = new CommandQueue();
        Assert.Equal(TimeSpan.FromSeconds(120), q.AbandonAfter);
        Assert.Equal(10, q.MaxFinishedEntries);
        Assert.Equal(1024L * 1024 * 1024, q.MaxFinishedBytes);
    }
}
