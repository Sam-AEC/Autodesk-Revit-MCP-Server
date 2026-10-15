using System;
using System.Linq;
using Xunit;

namespace RevitBridge.Tests;

public class NoAutodeskReferenceTests
{
    [Fact]
    public void Test_assembly_does_not_reference_any_Autodesk_assembly()
    {
        var names = typeof(NoAutodeskReferenceTests).Assembly.GetReferencedAssemblies().Select(a => a.Name ?? "").ToArray();
        Assert.DoesNotContain(names, n => n.StartsWith("RevitAPI", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(names, n => n.StartsWith("AdWindows", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(names, n => n.StartsWith("Autodesk", StringComparison.OrdinalIgnoreCase));
    }
}
