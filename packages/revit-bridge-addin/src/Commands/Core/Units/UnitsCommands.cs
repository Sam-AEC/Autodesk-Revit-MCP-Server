using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Core.Units
{
    /// <summary>
    /// Unit conversion and formatting commands
    /// UnitUtils is #15 ranked API (Score: 275) - essential for international work
    /// </summary>
    public static class UnitsCommands
    {
        #region 1. Convert to Internal Units

        public static object ConvertToInternalUnits(UIApplication app, JsonElement payload)
        {
            double value = payload.GetProperty("value").GetDouble();
            string unitType = payload.GetProperty("unit_type").GetString(); // length, area, volume, angle
            string fromUnit = payload.GetProperty("from_unit").GetString(); // meters, millimeters, feet, inches, etc.

            ForgeTypeId specTypeId = GetSpecTypeId(unitType);
            ForgeTypeId unitTypeId = GetUnitTypeId(fromUnit);

            double internalValue = UnitUtils.ConvertToInternalUnits(value, unitTypeId);

            return new
            {
                originalValue = value,
                originalUnit = fromUnit,
                internalValue = internalValue,
                internalUnit = "feet (Revit internal)",
                unitType = unitType
            };
        }

        #endregion

        #region 2. Convert from Internal Units

        public static object ConvertFromInternalUnits(UIApplication app, JsonElement payload)
        {
            double value = payload.GetProperty("value").GetDouble();
            string unitType = payload.GetProperty("unit_type").GetString();
            string toUnit = payload.GetProperty("to_unit").GetString();

            ForgeTypeId specTypeId = GetSpecTypeId(unitType);
            ForgeTypeId unitTypeId = GetUnitTypeId(toUnit);

            double convertedValue = UnitUtils.ConvertFromInternalUnits(value, unitTypeId);

            return new
            {
                internalValue = value,
                internalUnit = "feet (Revit internal)",
                convertedValue = convertedValue,
                convertedUnit = toUnit,
                unitType = unitType
            };
        }

        #endregion

        #region 3. Get Project Units

        public static object GetProjectUnits(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            Units units = doc.GetUnits();

            var unitSettings = new Dictionary<string, object>();

            // Get common unit types
            var commonSpecs = new[]
            {
                (name: "Length", id: SpecTypeId.Length),
                (name: "Area", id: SpecTypeId.Area),
                (name: "Volume", id: SpecTypeId.Volume),
                (name: "Angle", id: SpecTypeId.Angle),
                (name: "Force", id: SpecTypeId.Force),
                (name: "Mass", id: SpecTypeId.Mass),
                (name: "Temperature", id: SpecTypeId.Temperature)
            };

            foreach (var spec in commonSpecs)
            {
                try
                {
                    FormatOptions formatOptions = units.GetFormatOptions(spec.id);
                    unitSettings[spec.name] = new
                    {
                        unitSymbol = LabelUtils.GetLabelForUnit(formatOptions.GetUnitTypeId()),
                        accuracy = formatOptions.Accuracy,
                        rounding = formatOptions.GetRoundingMethod().ToString(),
                        suppressTrailingZeros = formatOptions.GetSuppressTrailingZeros(),
                        suppressLeadingZeros = formatOptions.GetSuppressLeadingZeros(),
                        useGrouping = formatOptions.GetUseGrouping()
                    };
                }
                catch
                {
                    // Skip if unit type not applicable
                }
            }

            return new
            {
                documentTitle = doc.Title,
                unitSettings = unitSettings
            };
        }

        #endregion

        #region 4. Set Project Units

        public static object SetProjectUnits(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string unitType = payload.GetProperty("unit_type").GetString();
            string unit = payload.GetProperty("unit").GetString();

            using (var trans = new Transaction(doc, "Set Project Units"))
            {
                trans.Start();

                Units units = doc.GetUnits();
                ForgeTypeId specTypeId = GetSpecTypeId(unitType);
                ForgeTypeId unitTypeId = GetUnitTypeId(unit);

                FormatOptions formatOptions = units.GetFormatOptions(specTypeId);
                formatOptions.SetUnitTypeId(unitTypeId);

                // Optional: Set accuracy if provided
                if (payload.TryGetProperty("accuracy", out var acc))
                {
                    formatOptions.Accuracy = acc.GetDouble();
                }

                units.SetFormatOptions(specTypeId, formatOptions);

                trans.Commit();

                return new
                {
                    success = true,
                    unitType = unitType,
                    unit = unit,
                    message = $"Project {unitType} units set to {unit}"
                };
            }
        }

        #endregion

        #region 5. Format Value with Units

        public static object FormatValueWithUnits(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            double value = payload.GetProperty("value").GetDouble();
            string unitType = payload.GetProperty("unit_type").GetString();
            bool includeSymbol = payload.TryGetProperty("include_symbol", out var incl) ? incl.GetBoolean() : true;

            ForgeTypeId specTypeId = GetSpecTypeId(unitType);
            Units units = doc.GetUnits();
            FormatOptions formatOptions = units.GetFormatOptions(specTypeId);

            FormatValueOptions formatValueOptions = new FormatValueOptions();
            formatValueOptions.SetFormatOptions(formatOptions);
            formatValueOptions.AppendUnitSymbol = includeSymbol;

            string formattedValue = UnitFormatUtils.Format(units, specTypeId, value, false, formatValueOptions);

            return new
            {
                originalValue = value,
                unitType = unitType,
                formattedValue = formattedValue,
                unitSymbol = includeSymbol ? LabelUtils.GetLabelForUnit(formatOptions.GetUnitTypeId()) : ""
            };
        }

        #endregion

        #region Helper Methods

        private static ForgeTypeId GetSpecTypeId(string unitType)
        {
            return unitType.ToLower() switch
            {
                "length" => SpecTypeId.Length,
                "area" => SpecTypeId.Area,
                "volume" => SpecTypeId.Volume,
                "angle" => SpecTypeId.Angle,
                "force" => SpecTypeId.Force,
                "mass" => SpecTypeId.Mass,
                "temperature" => SpecTypeId.Temperature,
                "currency" => SpecTypeId.Currency,
                "slope" => SpecTypeId.Slope,
                "distance" => SpecTypeId.Distance,
                "speed" => SpecTypeId.Speed,
                _ => throw new Exception($"Unknown unit type: {unitType}")
            };
        }

        private static ForgeTypeId GetUnitTypeId(string unit)
        {
            return unit.ToLower() switch
            {
                // Length
                "meters" or "m" => UnitTypeId.Meters,
                "millimeters" or "mm" => UnitTypeId.Millimeters,
                "centimeters" or "cm" => UnitTypeId.Centimeters,
                "feet" or "ft" => UnitTypeId.Feet,
                "inches" or "in" => UnitTypeId.Inches,
                "feet_fractional_inches" => UnitTypeId.FeetFractionalInches,

                // Area
                "square_meters" or "m2" => UnitTypeId.SquareMeters,
                "square_feet" or "ft2" => UnitTypeId.SquareFeet,
                "square_inches" or "in2" => UnitTypeId.SquareInches,

                // Volume
                "cubic_meters" or "m3" => UnitTypeId.CubicMeters,
                "cubic_feet" or "ft3" => UnitTypeId.CubicFeet,
                "liters" or "l" => UnitTypeId.Liters,
                "gallons" => UnitTypeId.Gallons,

                // Angle
                "degrees" or "deg" => UnitTypeId.Degrees,
                "radians" or "rad" => UnitTypeId.Radians,
                "gradians" or "grad" => UnitTypeId.Gradians,

                // Force
                "newtons" or "n" => UnitTypeId.Newtons,
                "kilonewtons" or "kn" => UnitTypeId.Kilonewtons,
                "pounds_force" or "lbf" => UnitTypeId.PoundsForce,
                "kips" => UnitTypeId.Kips,

                // Mass
                "kilograms" or "kg" => UnitTypeId.Kilograms,
                "pounds_mass" or "lbm" => UnitTypeId.PoundsMass,
                "tons" => UnitTypeId.Tons,

                // Temperature
                "celsius" or "c" => UnitTypeId.Celsius,
                "fahrenheit" or "f" => UnitTypeId.Fahrenheit,
                "kelvin" or "k" => UnitTypeId.Kelvin,

                _ => throw new Exception($"Unknown unit: {unit}")
            };
        }

        #endregion
    }
}
