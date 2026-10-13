using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
namespace ParameterRegression;
class UIApplication { public UIDocument ActiveUIDocument { get; set; } }
class UIDocument { public Document Document { get; set; } }
class Document { public Element Element; public Element GetElement(ElementId id) => Element; }
class ElementId { public ElementId(long id) { } }
class Element { public List<Parameter> Parameters = new(); public string Name => "Villa"; }
class Definition { public string Name { get; set; } }
enum StorageType { String }
class Parameter
{
    public bool HasValue = true;
    public Definition Definition { get; set; }
    public string Value;
    public StorageType StorageType => StorageType.String;
    public bool IsReadOnly { get; set; }
    public bool IsShared { get; set; }
    public Guid SharedGuid;
    public int GuidReads;
    public Guid GUID
    {
        get
        {
            GuidReads++;
            if (!IsShared) throw new InvalidOperationException("Parameter is not a shared parameter.");
            return SharedGuid;
        }
    }
}
static class Factory
{
    private static string GetParameterValueAsString(Parameter p) => p.Value;
    private static string GetDefinitionDataTypeName(Definition d) => "Text";
    /* PRODUCTION_METHOD */
}
static class Program
{
    static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }
    public static void Run()
    {
        var ordinary = new Parameter { Definition = new Definition { Name = "Mark" }, Value = "Villa-1" };
        var shared = new Parameter { Definition = new Definition { Name = "SharedCode" }, Value = "HJM", IsShared = true,
            IsReadOnly = true, SharedGuid = Guid.Parse("13ed4b47-2a75-4b9d-b73f-74da2e5e4715") };
        var empty = new Parameter { Definition = new Definition { Name = "Empty" }, HasValue = false };
        var element = new Element { Parameters = new() { ordinary, shared, empty } };
        var app = new UIApplication { ActiveUIDocument = new UIDocument { Document = new Document { Element = element } } };
        using var payload = JsonDocument.Parse("{\"element_id\":23841924}");
        var result = Factory.ExecuteGetElementParameters(app, payload.RootElement);
        using var output = JsonDocument.Parse(JsonSerializer.Serialize(result));
        var data = output.RootElement;
        var parameters = data.GetProperty("parameters");
        Check(data.GetProperty("element_id").GetInt32() == 23841924, "Element id changed");
        Check(data.GetProperty("parameter_count").GetInt32() == 2, "Valued parameters must survive; empty ones stay omitted");
        Check(parameters[0].GetProperty("guid").ValueKind == JsonValueKind.Null, "Ordinary GUID should serialize as null");
        Check(!parameters[0].GetProperty("is_shared").GetBoolean(), "Ordinary shared metadata changed");
        Check(parameters[0].GetProperty("name").GetString() == "Mark", "Ordinary name lost");
        Check(parameters[0].GetProperty("value").GetString() == "Villa-1", "Ordinary value lost");
        Check(parameters[1].GetProperty("guid").GetString() == shared.SharedGuid.ToString(), "Shared GUID changed");
        Check(parameters[1].GetProperty("is_shared").GetBoolean(), "Shared metadata changed");
        Check(parameters[1].GetProperty("is_read_only").GetBoolean(), "Read-only metadata changed");
        Check(ordinary.GuidReads == 0 && shared.GuidReads == 1 && empty.GuidReads == 0, "Invalid GUID access");
        element.Parameters = new() { ordinary };
        using var second = JsonDocument.Parse("{\"element_id\":23841925}");
        using var onlyOrdinary = JsonDocument.Parse(JsonSerializer.Serialize(Factory.ExecuteGetElementParameters(app, second.RootElement)));
        Check(onlyOrdinary.RootElement.GetProperty("parameter_count").GetInt32() == 1, "All non-shared parameter read failed");
        Check(ordinary.GuidReads == 0, "Non-shared GUID getter used");
        Console.WriteLine("PASS: actual parameter reader handles mixed and all-non-shared parameters, preserves shared GUID/metadata, emits null ordinary GUID, and skips empty values.");
    }
}


