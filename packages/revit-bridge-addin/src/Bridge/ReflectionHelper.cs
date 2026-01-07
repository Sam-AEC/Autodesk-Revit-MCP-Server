using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Autodesk.Revit.DB;

namespace RevitBridge.Bridge
{
    public static class ReflectionHelper
    {
        // transient object registry (for things that aren't Elements, e.g. XYZ points, Curves)
        private static Dictionary<string, object> _objectRegistry = new Dictionary<string, object>();
        private static int _objectIdCounter = 0;

        public static string RegisterObject(object obj)
        {
            if (obj == null) return null;
            if (obj is Element elem) return elem.Id.ToString(); // Elements use their native ID

            string id = $"obj_{++_objectIdCounter}";
            _objectRegistry[id] = obj;
            return id;
        }

        public static object GetObject(string id, Document doc)
        {
            if (string.IsNullOrEmpty(id)) return null;

            // Check if it's a register object
            if (_objectRegistry.ContainsKey(id)) return _objectRegistry[id];

            // Check if it's an Element ID
            if (int.TryParse(id, out int elemIdInt))
            {
                return doc.GetElement(new ElementId((long)elemIdInt));
            }
            // For 2024+, ElementId is long, but sticking to int parsing for compatibility/simplicity where possible or try long
            if (long.TryParse(id, out long elemIdLong))
            {
                 return doc.GetElement(new ElementId(elemIdLong));
            }

            return null;
        }

        public static void ClearRegistry()
        {
            _objectRegistry.Clear();
            _objectIdCounter = 0;
        }

        public static object ParseArgument(JsonElement arg, Document doc)
        {
            switch (arg.ValueKind)
            {
                case JsonValueKind.String:
                    string s = arg.GetString();
                    // Check for object reference syntax "@obj_123" or just "obj_123"? 
                    // Let's assume explicit object ref object structure is passed like {"type": "ref", "id": "..."} 
                    // OR simple strings are just strings. 
                    // But wait, the LLM might pass "Wall" as a string for an enum.
                    return s;
                
                case JsonValueKind.Number:
                    if (arg.TryGetInt32(out int i)) return i;
                    return arg.GetDouble();

                case JsonValueKind.True: return true;
                case JsonValueKind.False: return false;
                case JsonValueKind.Null: return null;

                case JsonValueKind.Object:
                    if (arg.TryGetProperty("type", out var typeProp) && typeProp.GetString() == "reference")
                    {
                        string refId = arg.GetProperty("id").GetString();
                        return GetObject(refId, doc);
                    }
                    // Handle simple structs like XYZ if passed as raw JSON?
                    if (arg.TryGetProperty("x", out _) && arg.TryGetProperty("y", out _) && arg.TryGetProperty("z", out _))
                    {
                        return new XYZ(arg.GetProperty("x").GetDouble(), arg.GetProperty("y").GetDouble(), arg.GetProperty("z").GetDouble());
                    }
                    return null; // or generic dict?
                
                default:
                    return null;
            }
        }

        public static Type ResolveType(string typeName)
        {
            // Try fundamental types
            if (typeName == "int" || typeName == "System.Int32") return typeof(int);
            if (typeName == "double" || typeName == "System.Double") return typeof(double);
            if (typeName == "string" || typeName == "System.String") return typeof(string);
            if (typeName == "bool" || typeName == "System.Boolean") return typeof(bool);

            // Search in loaded assemblies (RevitAPI, RevitAPIUI)
            var assemblies = AppDomain.CurrentDomain.GetAssemblies()
                .Where(a => a.FullName.StartsWith("RevitAPI") || a.FullName.StartsWith("System"));
            
            foreach (var asm in assemblies)
            {
                var type = asm.GetType(typeName) ?? asm.GetType("Autodesk.Revit.DB." + typeName) ?? asm.GetType("Autodesk.Revit.UI." + typeName);
                if (type != null) return type;
            }

            return null;
        }

        public static object InvokeMethod(Document doc, string typeName, string methodName, JsonElement argsElement, string targetId = null)
        {
            Type type = ResolveType(typeName);
            if (type == null) throw new Exception($"Type '{typeName}' not found.");

            object target = null;
            if (!string.IsNullOrEmpty(targetId))
            {
                target = GetObject(targetId, doc);
                if (target == null) throw new Exception($"Target object '{targetId}' not found.");
            }

            // Parse arguments
            List<object> args = new List<object>();
            if (argsElement.ValueKind == JsonValueKind.Array)
            {
                foreach (var argJson in argsElement.EnumerateArray())
                {
                    args.Add(ParseArgument(argJson, doc));
                }
            }

            // Handle Constructor
            if (methodName == "new" || methodName == "ctor")
            {
                var constructors = type.GetConstructors().Where(c => c.GetParameters().Length == args.Count).ToList();
                if (constructors.Count == 0) throw new Exception($"Constructor with {args.Count} arguments not found on type '{type.Name}'.");
                
                var ctor = constructors.First();
                var ctorParams = ctor.GetParameters();
                object[] ctorArgs = new object[args.Count];
                
                for (int i = 0; i < args.Count; i++)
                {
                    var targetType = ctorParams[i].ParameterType;
                    var val = args[i];
                    
                    if (targetType.IsEnum)
                    {
                        if (val is string s) val = Enum.Parse(targetType, s);
                        else if (val is int n) val = Enum.ToObject(targetType, n);
                    }
                    
                    if (val is IConvertible && !targetType.IsAssignableFrom(val.GetType()))
                    {
                       try { val = Convert.ChangeType(val, targetType); } catch {}
                    }
                    ctorArgs[i] = val;
                }

                object instance = ctor.Invoke(ctorArgs);
                string regId = RegisterObject(instance);
                return new { type = "reference", id = regId, class_name = instance.GetType().Name, str = instance.ToString() };
            }

            // Find best matching method (Simplistic matching for MVP)
            var flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.FlattenHierarchy;
            var methods = type.GetMethods(flags).Where(m => m.Name == methodName && m.GetParameters().Length == args.Count).ToList();

            if (methods.Count == 0) throw new Exception($"Method '{methodName}' with {args.Count} arguments not found on type '{type.Name}'.");
            
            // Try to pick the first one that works (risky but MVP)
            MethodInfo methodToInvoke = methods.First();
            // TODO: Better parameter type checking/casting

            // Cast args to match signature
            var parameters = methodToInvoke.GetParameters();
            object[] finalArgs = new object[args.Count];
            for (int i = 0; i < args.Count; i++)
            {
                var targetType = parameters[i].ParameterType;
                var val = args[i];
                
                // Handle Enums conversions from String/Int
                if (targetType.IsEnum)
                {
                    if (val is string s) val = Enum.Parse(targetType, s);
                    else if (val is int n) val = Enum.ToObject(targetType, n);
                }
                
                // Convert.ChangeType for primitives
                if (val is IConvertible && !targetType.IsAssignableFrom(val.GetType()))
                {
                   try { val = Convert.ChangeType(val, targetType); } catch {}
                }

                finalArgs[i] = val;
            }

            // Invoke
            object result = methodToInvoke.Invoke(target, finalArgs);

            // Process result
            if (result == null) return null;
            if (result is ElementId eid) return eid.Value; // Return raw int/long
            if (result.GetType().IsPrimitive || result is string) return result;

            // It's an object, register it
            string resultRegId = RegisterObject(result);
            return new { type = "reference", id = resultRegId, class_name = result.GetType().Name, str = result.ToString() };
        }
    }
}
