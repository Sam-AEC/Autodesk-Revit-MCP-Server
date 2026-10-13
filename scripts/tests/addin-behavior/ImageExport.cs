using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
namespace ExportRegression;
class UIApplication { public UIDocument ActiveUIDocument { get; set; } }
class UIDocument { public Document Document { get; set; } }
class Document { public View View = new(); public Action<ImageExportOptions> Export; public object GetElement(ElementId id) => View; public void ExportImage(ImageExportOptions options) => Export(options); }
class ElementId { public ElementId(long id) { } }
class View { public ElementId Id = new(23840425); public string Name => "AMB_3D Villa"; }
enum ZoomFitType { FitToPage }
enum ImageResolution { DPI_150 }
enum FitDirectionType { Horizontal, Vertical }
enum ImageFileType { PNG, JPEGLossless, BMP, TIFF }
enum ExportRange { SetOfViews }
class ImageExportOptions
{
    public ZoomFitType ZoomType { get; set; }
    public int PixelSize { get; set; }
    public ImageResolution ImageResolution { get; set; }
    public string FilePath { get; set; }
    public FitDirectionType FitDirection { get; set; }
    public ImageFileType HLRandWFViewsFileType { get; set; }
    public ImageFileType ShadowViewsFileType { get; set; }
    public ExportRange ExportRange { get; set; }
    public void SetViewsAndSheets(List<ElementId> ids) { }
}
class Transaction : IDisposable { public void Start() { } public void Commit() { } public void Dispose() { } }
static class BridgeCommandFactory
{
    public static Transaction CreateTransaction(Document doc, string name) => new();
    /* PRODUCTION_METHOD */
}
static class Program
{
    static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    static JsonDocument Run(UIApplication app, string outputPath, int? width = null, int? height = null)
    {
        using var payload = JsonDocument.Parse(JsonSerializer.Serialize(new { view_id = 23840425, output_path = outputPath, width, height }));
        return JsonDocument.Parse(JsonSerializer.Serialize(BridgeCommandFactory.ExecuteExportImage(app, payload.RootElement)));
    }
    public static void Run()
    {
        var folder = Path.Combine(AppContext.BaseDirectory, "export-artifacts");
        Directory.CreateDirectory(folder);
        var doc = new Document();
        var app = new UIApplication { ActiveUIDocument = new UIDocument { Document = doc } };
        var requested = Path.Combine(folder, "villa-before.png");
        var actual = Path.Combine(folder, "villa-before - 3D View - AMB_3D Villa.png");
        doc.Export = options =>
        {
            Check(options.FilePath == Path.Combine(folder, "villa-before"), "FilePath must include filename prefix");
            Check(options.PixelSize == 1800 && options.FitDirection == FitDirectionType.Horizontal, "Width must govern fit pixels");
            Check(options.HLRandWFViewsFileType == ImageFileType.PNG && options.ShadowViewsFileType == ImageFileType.PNG, "All view styles must use PNG");
            File.WriteAllBytes(actual, new byte[] { 1, 2, 3, 4 });
            File.WriteAllText(Path.Combine(folder, "villa-before-log.txt"), "not an image");
            File.WriteAllBytes(Path.Combine(folder, "unrelated.png"), new byte[] { 1 });
        };
        using var first = Run(app, requested, 1800);
        var output = first.RootElement;
        Check(output.GetProperty("status").GetString() == "success" && output.GetProperty("file_exists").GetBoolean(), "New export must succeed");
        Check(output.GetProperty("file_path").GetString() == actual && File.Exists(output.GetProperty("file_path").GetString()), "Report actual suffix filename");
        Check(output.GetProperty("file_paths").GetArrayLength() == 1 && output.GetProperty("file_size_bytes").GetInt64() == 4, "Ignore nonimages/unrelated files");
        doc.Export = _ => { };
        using var stale = Run(app, requested);
        Check(stale.RootElement.GetProperty("status").GetString() == "error" && !stale.RootElement.GetProperty("file_exists").GetBoolean(), "Stale image must not count as export");
        Check(stale.RootElement.GetProperty("file_path").ValueKind == JsonValueKind.Null, "Missing artifact must not invent path");
        doc.Export = _ => File.WriteAllBytes(actual, new byte[] { 1, 2, 3, 4, 5 });
        using var changed = Run(app, requested);
        Check(changed.RootElement.GetProperty("status").GetString() == "success" && changed.RootElement.GetProperty("file_size_bytes").GetInt64() == 5, "Changed existing image must count");
        doc.Export = options =>
        {
            Check(options.PixelSize == 900 && options.FitDirection == FitDirectionType.Vertical, "Height-only fit must be vertical");
            Check(options.ShadowViewsFileType == ImageFileType.JPEGLossless, "Infer requested JPG format");
            File.WriteAllBytes(options.FilePath + " - Villa.jpg", new byte[] { 8 });
        };
        using var heightOnly = Run(app, Path.Combine(folder, "height-only.jpg"), height: 900);
        Check(heightOnly.RootElement.GetProperty("status").GetString() == "success", "JPG height-only export failed");
        doc.Export = options => File.WriteAllBytes(options.FilePath + " - Villa.png", Array.Empty<byte>());
        using var empty = Run(app, Path.Combine(folder, "empty.png"));
        Check(empty.RootElement.GetProperty("status").GetString() == "error", "Empty file must not count");
        Console.WriteLine("PASS: actual export method reports real suffix artifacts, rejects missing/stale/empty output, honors width/height and all-view format, and detects changed existing files.");
    }
}


