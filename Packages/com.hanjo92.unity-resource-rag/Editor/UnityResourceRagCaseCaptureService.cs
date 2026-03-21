using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagCaseCaptureResult
    {
        public bool Success => Errors.Count == 0;
        public List<string> Errors { get; } = new List<string>();
        public string Summary { get; set; } = string.Empty;
        public string OutputDirectory { get; set; } = string.Empty;
        public string MarkdownReportPath { get; set; } = string.Empty;
        public string JsonReportPath { get; set; } = string.Empty;
    }

    public static class UnityResourceRagCaseCaptureService
    {
        public static UnityResourceRagCaseCaptureResult Export(
            UnityResourceRagEditorSettings settings,
            UnityResourceRagLocalToolResult buildResult,
            UnityResourceRagLocalToolResult captureResult,
            UnityResourceRagLocalToolResult repairResult,
            string caseName,
            string notes)
        {
            settings.EnsureDefaults();
            var result = new UnityResourceRagCaseCaptureResult();

            if (buildResult == null || !buildResult.Success || buildResult.Payload == null)
            {
                result.Errors.Add("A successful UI build result is required before a case report can be created.");
                result.Summary = BuildSummary(result);
                return result;
            }

            string effectiveCaseName = ResolveCaseName(settings, buildResult.Payload, caseName);
            string timestamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
            string slug = Slugify(effectiveCaseName);
            string outputDirectory = Path.Combine(settings.UnityProjectPath, "Library", "ResourceRag", "Cases", $"{timestamp}-{slug}");
            Directory.CreateDirectory(outputDirectory);

            JObject buildPayload = buildResult.Payload;
            JObject capturePayload = captureResult?.Payload;
            JObject repairPayload = repairResult?.Payload;

            var jsonPayload = new JObject
            {
                ["generatedAtLocal"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                ["caseName"] = effectiveCaseName,
                ["unityProjectPath"] = settings.UnityProjectPath,
                ["referenceImage"] = string.IsNullOrWhiteSpace(settings.ReferenceImagePath) ? null : settings.ReferenceImagePath,
                ["goal"] = settings.Goal,
                ["screenName"] = settings.ScreenName,
                ["route"] = UnityResourceRagReportFormatter.ExtractRouteLabel(buildPayload),
                ["doctorStatus"] = buildPayload.SelectToken("doctor.overallStatus")?.ToString(),
                ["build"] = new JObject
                {
                    ["blueprintPath"] = UnityResourceRagReportFormatter.ExtractBlueprintPath(buildPayload),
                    ["handoffPath"] = UnityResourceRagReportFormatter.ExtractHandoffPath(buildPayload),
                    ["outputDirectory"] = UnityResourceRagReportFormatter.ExtractOutputDirectory(buildPayload),
                    ["appliedRootName"] = UnityResourceRagReportFormatter.ExtractAppliedRootName(buildPayload),
                    ["verifyTarget"] = UnityResourceRagReportFormatter.ExtractVerifyTarget(buildPayload),
                    ["nextActions"] = JArray.FromObject(UnityResourceRagReportFormatter.CollectStringArray(buildPayload["nextActions"] as JArray)),
                },
                ["capture"] = capturePayload == null
                    ? null
                    : new JObject
                    {
                        ["capturedPath"] = capturePayload.Value<string>("capturedPath"),
                        ["capturedPathRelative"] = capturePayload.Value<string>("capturedPathRelative"),
                        ["screenshotsFolder"] = capturePayload.Value<string>("screenshotsFolder"),
                    },
                ["repair"] = repairPayload == null
                    ? null
                    : new JObject
                    {
                        ["verificationReport"] = repairPayload.Value<string>("verificationReport"),
                        ["repairHandoff"] = repairPayload.Value<string>("repairHandoff"),
                        ["workflowReport"] = repairPayload.Value<string>("workflowReport"),
                        ["hasErrors"] = repairPayload.Value<bool?>("hasErrors") ?? false,
                    },
                ["notes"] = notes ?? string.Empty,
            };

            string jsonPath = Path.Combine(outputDirectory, "case-report.json");
            string markdownPath = Path.Combine(outputDirectory, "case-report.md");

            File.WriteAllText(jsonPath, jsonPayload.ToString(Formatting.Indented) + "\n", new UTF8Encoding(false));
            File.WriteAllText(markdownPath, BuildMarkdownReport(jsonPayload), new UTF8Encoding(false));

            result.OutputDirectory = outputDirectory;
            result.MarkdownReportPath = markdownPath;
            result.JsonReportPath = jsonPath;
            result.Summary = BuildSummary(result);
            return result;
        }

        private static string BuildMarkdownReport(JObject payload)
        {
            JObject build = payload["build"] as JObject;
            JObject capture = payload["capture"] as JObject;
            JObject repair = payload["repair"] as JObject;
            var builder = new StringBuilder();

            builder.AppendLine("# Quality Case Report");
            builder.AppendLine();
            builder.AppendLine($"- Date: {payload.Value<string>("generatedAtLocal")}");
            builder.AppendLine($"- Case: {payload.Value<string>("caseName")}");
            builder.AppendLine($"- Project: {payload.Value<string>("unityProjectPath")}");
            builder.AppendLine($"- Flow: {payload.Value<string>("route")}");
            builder.AppendLine($"- Doctor: {payload.Value<string>("doctorStatus") ?? "unknown"}");
            builder.AppendLine();

            builder.AppendLine("## Inputs");
            builder.AppendLine();
            builder.AppendLine($"- Reference image: {FormatValue(payload.Value<string>("referenceImage"))}");
            builder.AppendLine($"- Goal: {FormatValue(payload.Value<string>("goal"))}");
            builder.AppendLine($"- Screen name: {FormatValue(payload.Value<string>("screenName"))}");
            builder.AppendLine();

            builder.AppendLine("## Build");
            builder.AppendLine();
            builder.AppendLine($"- Blueprint: {FormatValue(build?.Value<string>("blueprintPath"))}");
            builder.AppendLine($"- Handoff: {FormatValue(build?.Value<string>("handoffPath"))}");
            builder.AppendLine($"- Output directory: {FormatValue(build?.Value<string>("outputDirectory"))}");
            builder.AppendLine($"- Applied root: {FormatValue(build?.Value<string>("appliedRootName"))}");
            builder.AppendLine($"- Verify target: {FormatValue(build?.Value<string>("verifyTarget"))}");
            AppendStringList(builder, "Suggested follow-up", build?["nextActions"] as JArray);

            builder.AppendLine("## Capture");
            builder.AppendLine();
            if (capture == null)
            {
                builder.AppendLine("- Capture result: not exported in this run");
            }
            else
            {
                builder.AppendLine($"- Screenshot: {FormatValue(capture.Value<string>("capturedPath"))}");
                builder.AppendLine($"- Unity asset path: {FormatValue(capture.Value<string>("capturedPathRelative"))}");
            }
            builder.AppendLine();

            builder.AppendLine("## Repair");
            builder.AppendLine();
            if (repair == null)
            {
                builder.AppendLine("- Repair handoff: not exported in this run");
            }
            else
            {
                builder.AppendLine($"- Verification report: {FormatValue(repair.Value<string>("verificationReport"))}");
                builder.AppendLine($"- Repair handoff: {FormatValue(repair.Value<string>("repairHandoff"))}");
                builder.AppendLine($"- Workflow report: {FormatValue(repair.Value<string>("workflowReport"))}");
                builder.AppendLine($"- Repair workflow errors: {(repair.Value<bool?>("hasErrors") ?? false ? "yes" : "no")}");
            }
            builder.AppendLine();

            builder.AppendLine("## Notes");
            builder.AppendLine();
            string notes = payload.Value<string>("notes");
            builder.AppendLine(string.IsNullOrWhiteSpace(notes) ? "- (add observations here)" : notes.Trim());
            builder.AppendLine();

            builder.AppendLine("## Follow-Up Checklist");
            builder.AppendLine();
            builder.AppendLine("- What matched the reference or intent well?");
            builder.AppendLine("- What looked wrong in asset choice, spacing, hierarchy, or typography?");
            builder.AppendLine("- Which retrieval, blueprint, or repair change would improve this case the most?");
            return builder.ToString();
        }

        private static void AppendStringList(StringBuilder builder, string label, JArray items)
        {
            builder.AppendLine($"- {label}:");
            if (items == null || items.Count == 0)
            {
                builder.AppendLine("  - (none)");
                builder.AppendLine();
                return;
            }

            foreach (JToken token in items)
            {
                string value = token?.ToString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    builder.AppendLine($"  - {value}");
                }
            }

            builder.AppendLine();
        }

        private static string ResolveCaseName(UnityResourceRagEditorSettings settings, JObject buildPayload, string caseName)
        {
            if (!string.IsNullOrWhiteSpace(caseName))
            {
                return caseName.Trim();
            }

            string fromBuild = UnityResourceRagReportFormatter.ExtractAppliedRootName(buildPayload);
            if (!string.IsNullOrWhiteSpace(fromBuild))
            {
                return fromBuild;
            }

            return settings.ScreenName;
        }

        private static string Slugify(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return "ui-case";
            }

            var builder = new StringBuilder();
            foreach (char character in value.Trim().ToLowerInvariant())
            {
                if ((character >= 'a' && character <= 'z') || (character >= '0' && character <= '9'))
                {
                    builder.Append(character);
                }
                else if (builder.Length == 0 || builder[builder.Length - 1] == '-')
                {
                    continue;
                }
                else
                {
                    builder.Append('-');
                }
            }

            string slug = builder.ToString().Trim('-');
            return string.IsNullOrWhiteSpace(slug) ? "ui-case" : slug;
        }

        private static string FormatValue(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? "(not set)" : value;
        }

        private static string BuildSummary(UnityResourceRagCaseCaptureResult result)
        {
            if (result.Success)
            {
                return "Saved the case export.";
            }

            return $"Failed to save the case export. ({result.Errors.Count} error)";
        }
    }
}
