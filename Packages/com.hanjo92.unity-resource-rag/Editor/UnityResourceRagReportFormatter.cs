using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor
{
    public enum UnityResourceRagReadinessLevel
    {
        Ready,
        Attention,
        Blocked,
    }

    public sealed class UnityResourceRagReadinessItem
    {
        public string Title { get; set; } = string.Empty;
        public UnityResourceRagReadinessLevel Level { get; set; }
        public string Summary { get; set; } = string.Empty;
        public string NextStep { get; set; } = string.Empty;
    }

    public static class UnityResourceRagReportFormatter
    {
        public static string FormatQuickSetupReport(UnityResourceRagQuickSetupResult result)
        {
            return string.Join(
                "\n",
                new[]
                {
                    result.Summary,
                    result.Steps.Count > 0 ? "Done:\n- " + string.Join("\n- ", result.Steps) : string.Empty,
                    result.Warnings.Count > 0 ? "Attention:\n- " + string.Join("\n- ", result.Warnings) : string.Empty,
                    result.Errors.Count > 0 ? "Blocked:\n- " + string.Join("\n- ", result.Errors) : string.Empty,
                }).Trim();
        }

        public static string FormatRuntimeBootstrapReport(UnityResourceRagRuntimeBootstrapResult result)
        {
            return string.Join(
                "\n",
                new[]
                {
                    result.Summary,
                    result.Steps.Count > 0 ? "Done:\n- " + string.Join("\n- ", result.Steps) : string.Empty,
                    result.Warnings.Count > 0 ? "Attention:\n- " + string.Join("\n- ", result.Warnings) : string.Empty,
                    result.Errors.Count > 0 ? "Blocked:\n- " + string.Join("\n- ", result.Errors) : string.Empty,
                    !string.IsNullOrWhiteSpace(result.RecommendedPythonExecutable) ? $"Python: {result.RecommendedPythonExecutable}" : string.Empty,
                }).Trim();
        }

        public static string FormatReadinessRefreshReport(UnityResourceRagEditorSettings settings, UnityResourceRagLocalToolResult doctorResult)
        {
            List<UnityResourceRagReadinessItem> items = BuildReadinessItems(settings, doctorResult);
            var lines = new List<string>
            {
                doctorResult != null && doctorResult.Success
                    ? "Readiness check completed."
                    : "Current readiness status summary:",
            };

            foreach (UnityResourceRagReadinessItem item in items)
            {
                lines.Add($"{DescribeReadinessLevel(item.Level)} - {item.Title}: {item.Summary}");
                if (!string.IsNullOrWhiteSpace(item.NextStep))
                {
                    lines.Add($"Next: {item.NextStep}");
                }
            }

            JArray nextActionItems = doctorResult != null ? doctorResult.Payload?["nextActions"] as JArray : null;
            List<string> nextActions = CollectStringArray(nextActionItems);
            if (nextActions.Count > 0)
            {
                lines.Add("Suggested next steps:");
                foreach (string action in nextActions)
                {
                    lines.Add("- " + action);
                }
            }

            if (doctorResult != null && !doctorResult.Success && !string.IsNullOrWhiteSpace(doctorResult.Error))
            {
                lines.Add("Attention:");
                lines.Add("- " + doctorResult.Error);
            }

            return string.Join("\n", lines);
        }

        public static List<UnityResourceRagReadinessItem> BuildReadinessItems(UnityResourceRagEditorSettings settings, UnityResourceRagLocalToolResult doctorResult)
        {
            var items = new List<UnityResourceRagReadinessItem>
            {
                BuildRepoItem(settings),
                BuildPythonItem(settings),
                BuildAuthItem(settings),
                BuildUnityMcpItem(settings, doctorResult?.Payload),
                BuildBuildInputItem(settings, doctorResult?.Payload),
            };

            return items;
        }

        public static string FormatCaseCaptureReport(UnityResourceRagCaseCaptureResult result)
        {
            if (result == null)
            {
                return "No case export result is available.";
            }

            var lines = new List<string>
            {
                result.Summary,
            };

            AppendIfPresent(lines, "Folder", result.OutputDirectory);
            AppendIfPresent(lines, "Markdown", result.MarkdownReportPath);
            AppendIfPresent(lines, "JSON", result.JsonReportPath);

            if (result.Errors.Count > 0)
            {
                lines.Add("Blocked:");
                foreach (string error in result.Errors)
                {
                    lines.Add("- " + error);
                }
            }
            else
            {
                lines.Add("Next:");
                lines.Add("- Add real project quality notes to `case-report.md` before attaching it to a GitHub issue or release follow-up.");
                lines.Add("- Reuse the same case folder as the comparison baseline when you revisit the same screen later.");
            }

            return string.Join("\n", lines);
        }

        public static string FormatBuildReport(UnityResourceRagLocalToolResult result)
        {
            if (result.Success)
            {
                return FormatSuccessfulBuildReport(result);
            }

            return FormatFailedBuildReport(result);
        }

        public static string FormatCaptureReport(UnityResourceRagLocalToolResult result)
        {
            if (!result.Success)
            {
                return "Failed to capture the result screenshot.\n" + (string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);
            }

            JObject payload = result.Payload;
            string screenshotPath = payload?.Value<string>("capturedPath") ?? "(not found)";
            string relativePath = payload?.Value<string>("capturedPathRelative") ?? string.Empty;
            var lines = new List<string>
            {
                "Saved the result screenshot.",
                $"Screenshot: {screenshotPath}",
            };
            if (!string.IsNullOrWhiteSpace(relativePath))
            {
                lines.Add($"Unity Asset Path: {relativePath}");
            }

            lines.Add("Next:");
            lines.Add("- Review the capture for spacing, asset choice, and hierarchy issues.");
            lines.Add("- If this was a reference-based build, you can run Repair Handoff from the same window.");
            return string.Join("\n", lines);
        }

        public static string FormatRepairReport(UnityResourceRagLocalToolResult result)
        {
            if (!result.Success)
            {
                return "Failed to create the repair handoff.\n" + (string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);
            }

            JObject payload = result.Payload;
            var lines = new List<string>
            {
                "Created the repair handoff.",
            };

            AppendIfPresent(lines, "Verification Report", payload?.Value<string>("verificationReport"));
            AppendIfPresent(lines, "Repair Handoff", payload?.Value<string>("repairHandoff"));
            AppendIfPresent(lines, "Workflow Report", payload?.Value<string>("workflowReport"));

            if ((payload?.Value<bool?>("hasErrors") ?? false))
            {
                lines.Add("Attention:");
                lines.Add("- The verification workflow reported one or more errors. Review the report file first.");
            }
            else
            {
                lines.Add("Next:");
                lines.Add("- Apply small follow-up fixes starting from the repair handoff.");
                lines.Add("- Capture the result again after changes and compare the new output.");
            }

            return string.Join("\n", lines);
        }

        public static string ExtractBlueprintPath(JObject buildPayload)
        {
            return FirstNonEmpty(
                buildPayload?.SelectToken("execution.draftBlueprint")?.ToString(),
                buildPayload?.SelectToken("execution.workflow.resolvedBlueprint")?.ToString(),
                buildPayload?.SelectToken("execution.resolvedBlueprint")?.ToString());
        }

        public static string ExtractHandoffPath(JObject buildPayload)
        {
            return FirstNonEmpty(
                buildPayload?.SelectToken("execution.handoffBundlePath")?.ToString(),
                buildPayload?.SelectToken("execution.workflow.mcpHandoffBundle")?.ToString());
        }

        public static string ExtractOutputDirectory(JObject buildPayload)
        {
            return FirstNonEmpty(
                buildPayload?.SelectToken("execution.outputDir")?.ToString(),
                Path.GetDirectoryName(ExtractBlueprintPath(buildPayload)));
        }

        public static JObject ExtractVerificationRequest(JObject buildPayload)
        {
            return buildPayload?.SelectToken("execution.verifyRequest") as JObject;
        }

        public static string ExtractVerifyTarget(JObject buildPayload)
        {
            return FirstNonEmpty(
                buildPayload?.SelectToken("execution.verifyRequest.parameters.view_target")?.ToString(),
                buildPayload?.SelectToken("execution.unityApply.response.data.rootName")?.ToString(),
                buildPayload?.SelectToken("execution.unityValidate.response.data.verificationHint.parameters.view_target")?.ToString());
        }

        public static string ExtractAppliedRootName(JObject buildPayload)
        {
            return FirstNonEmpty(
                buildPayload?.SelectToken("execution.unityApply.response.data.rootName")?.ToString(),
                ExtractVerifyTarget(buildPayload));
        }

        public static string ExtractRouteLabel(JObject buildPayload)
        {
            string selectedPath = buildPayload?.Value<string>("selectedPath") ?? string.Empty;
            return string.Equals(selectedPath, "reference_first_pass", StringComparison.OrdinalIgnoreCase)
                ? "Reference-first build"
                : string.Equals(selectedPath, "catalog_draft", StringComparison.OrdinalIgnoreCase)
                    ? "Catalog-first draft"
                    : "UI build";
        }

        private static UnityResourceRagReadinessItem BuildRepoItem(UnityResourceRagEditorSettings settings)
        {
            if (UnityResourceRagEditorSettings.IsSidecarRepoRoot(settings.SidecarRepoRoot))
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Sidecar Repo",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = "Found a full unity-resource-rag checkout for the one-click workflow.",
                    NextStep = settings.SidecarRepoRoot,
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Sidecar Repo",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "The current path is not enough to run the Python sidecar.",
                NextStep = "Set Sidecar Repo Root to a full unity-resource-rag checkout path.",
            };
        }

        private static UnityResourceRagReadinessItem BuildPythonItem(UnityResourceRagEditorSettings settings)
        {
            string repoRoot = settings.SidecarRepoRoot;
            string repoVenvPython = UnityResourceRagEditorSettings.GetRepositoryVenvPythonPath(repoRoot);
            if (!string.IsNullOrWhiteSpace(repoVenvPython) && UnityResourceRagEditorSettings.IsPythonReadyForSidecar(repoVenvPython, repoRoot))
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Python Runtime",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = "The repo-local Python runtime is ready.",
                    NextStep = repoVenvPython,
                };
            }

            if (UnityResourceRagEditorSettings.TryDetectWorkingPythonExecutable(repoRoot, out string detectedPython))
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Python Runtime",
                    Level = UnityResourceRagReadinessLevel.Attention,
                    Summary = "A working Python executable was found, but the repo-local runtime is not pinned yet.",
                    NextStep = $"Run Bootstrap Python Runtime or continue with `{detectedPython}` as-is.",
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Python Runtime",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "No Python runtime is currently ready to load the sidecar dependencies.",
                NextStep = "Run Bootstrap Python Runtime to prepare `.venv` and install the required packages.",
            };
        }

        private static UnityResourceRagReadinessItem BuildAuthItem(UnityResourceRagEditorSettings settings)
        {
            switch (settings.AuthMode)
            {
                case UnityResourceRagAuthMode.UseExistingCodexLogin:
                    if (settings.HasReadableCodexAuthFile)
                    {
                        return new UnityResourceRagReadinessItem
                        {
                            Title = "AI Access",
                            Level = UnityResourceRagReadinessLevel.Ready,
                            Summary = "Your current Codex sign-in is ready to use.",
                            NextStep = "No extra key entry is required unless you want to override the default auth file location.",
                        };
                    }

                    return new UnityResourceRagReadinessItem
                    {
                        Title = "AI Access",
                        Level = UnityResourceRagReadinessLevel.Attention,
                        Summary = "No Codex sign-in was found in the default auth file locations yet.",
                        NextStep = "Sign in to Codex, point the window to a custom auth file override, or switch to Offline local for a first test.",
                    };
                case UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable:
                    if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(settings.ProviderApiKeyEnv)))
                    {
                        return new UnityResourceRagReadinessItem
                        {
                            Title = "AI Access",
                            Level = UnityResourceRagReadinessLevel.Ready,
                            Summary = "An API key is available through the configured environment variable.",
                            NextStep = $"Current variable name: {settings.ProviderApiKeyEnv}",
                        };
                    }

                    return new UnityResourceRagReadinessItem
                    {
                        Title = "AI Access",
                        Level = UnityResourceRagReadinessLevel.Attention,
                        Summary = "No API key value was found in the configured environment variable.",
                        NextStep = $"Set `{settings.ProviderApiKeyEnv}` in your environment or switch back to Use my Codex sign-in.",
                    };
                default:
                    return new UnityResourceRagReadinessItem
                    {
                        Title = "AI Access",
                        Level = UnityResourceRagReadinessLevel.Ready,
                        Summary = "Offline local fallback is selected for this project.",
                        NextStep = "This mode is useful when you only want to validate catalog-first draft and apply behavior without hosted model access.",
                    };
            }
        }

        private static UnityResourceRagReadinessItem BuildUnityMcpItem(UnityResourceRagEditorSettings settings, JObject doctorPayload)
        {
            JObject check = FindDoctorCheck(doctorPayload, "unity_mcp");
            if (check == null)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Attention,
                    Summary = "No readiness refresh has been run yet.",
                    NextStep = "Press Refresh Readiness to verify the Unity MCP connection.",
                };
            }

            string status = check.Value<string>("status") ?? string.Empty;
            JObject details = check["details"] as JObject;
            bool hasMissingTools = (details?["missingTools"] as JArray)?.Count > 0;
            bool hasMissingResources = (details?["missingResources"] as JArray)?.Count > 0;

            if (status == "ok")
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = "The Unity Editor connection and required build tools are ready.",
                    NextStep = settings.UnityMcpRpcUrl,
                };
            }

            if (hasMissingTools || status == "error")
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Blocked,
                    Summary = "The Unity Editor is reachable, but one or more required build tools are still missing.",
                    NextStep = "Run Quick Setup again and verify the Local HTTP Server and custom tool exposure.",
                };
            }

            if (hasMissingResources)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Attention,
                    Summary = "UI builds can continue, but only part of the catalog or resource information is visible.",
                    NextStep = "Most builds can still continue. Investigate further only if you need raw catalog browsing.",
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Unity Editor Connection",
                Level = UnityResourceRagReadinessLevel.Attention,
                Summary = "The Unity Editor readiness state still has items that need attention.",
                NextStep = FirstNonEmpty(
                    (check["nextActions"] as JArray)?.First?.ToString(),
                    "Run Quick Setup or Refresh Readiness again."),
            };
        }

        private static UnityResourceRagReadinessItem BuildBuildInputItem(UnityResourceRagEditorSettings settings, JObject doctorPayload)
        {
            JObject catalogCheck = FindDoctorCheck(doctorPayload, "catalog");
            bool hasReference = !string.IsNullOrWhiteSpace(settings.ReferenceImagePath) && File.Exists(settings.ReferenceImagePath);
            bool hasDraftInput = !string.IsNullOrWhiteSpace(settings.Goal) || !string.IsNullOrWhiteSpace(settings.Title) || !string.IsNullOrWhiteSpace(settings.Body);
            bool catalogReady = string.Equals(catalogCheck?.Value<string>("status"), "ok", StringComparison.OrdinalIgnoreCase);
            string templateLabel = DescribeDraftTemplate(settings.DraftTemplateMode);

            if (hasReference)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Build Input",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = catalogReady
                        ? "The reference image and project catalog are ready."
                        : "The reference image is ready, and the catalog will be checked again during the build if needed.",
                    NextStep = settings.ReferenceImagePath,
                };
            }

            if (hasDraftInput)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Build Input",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = catalogReady
                        ? $"The inputs required for a {templateLabel.ToLowerInvariant()} catalog-first draft are ready."
                        : $"Goal, title, and body are ready for a {templateLabel.ToLowerInvariant()} draft. The first build will create the catalog if it does not exist yet.",
                    NextStep = $"{templateLabel}: " + (string.IsNullOrWhiteSpace(settings.Goal) ? settings.Title : settings.Goal),
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Build Input",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "A reference image or catalog-first draft input is required.",
                NextStep = "Provide a Reference Image or fill in Goal, Title, and Body.",
            };
        }

        private static string FormatSuccessfulBuildReport(UnityResourceRagLocalToolResult result)
        {
            JObject payload = result.Payload;
            if (payload == null)
            {
                return string.IsNullOrWhiteSpace(result.Summary) ? "UI build completed." : result.Summary;
            }

            string routeLabel = ExtractRouteLabel(payload);
            string blueprintPath = ExtractBlueprintPath(payload);
            string handoffPath = ExtractHandoffPath(payload);
            string applySummary = BuildApplySummary(payload.SelectToken("execution.unityApply") as JObject);
            string templateMode = payload.SelectToken("execution.templateMode")?.ToString() ?? string.Empty;

            var lines = new List<string>
            {
                "UI build completed.",
                $"Flow: {routeLabel}",
            };
            if (!string.IsNullOrWhiteSpace(templateMode) && string.Equals(routeLabel, "Catalog-first draft", StringComparison.OrdinalIgnoreCase))
            {
                lines.Add($"Draft Template: {DescribeTemplateMode(templateMode)}");
            }

            AppendIfPresent(lines, "Blueprint", blueprintPath);
            AppendIfPresent(lines, "Handoff", handoffPath);
            AppendIfPresent(lines, "Unity Apply", applySummary);

            List<string> warnings = CollectDoctorWarnings(payload.SelectToken("doctor.checks") as JArray);
            if (warnings.Count > 0)
            {
                lines.Add("Attention:");
                foreach (string warning in warnings)
                {
                    lines.Add("- " + warning);
                }
            }

            List<string> nextActions = CollectStringArray(payload["nextActions"] as JArray);
            if (nextActions.Count > 0)
            {
                lines.Add("Next:");
                foreach (string action in nextActions)
                {
                    lines.Add("- " + action);
                }
            }

            return string.Join("\n", lines);
        }

        private static string FormatFailedBuildReport(UnityResourceRagLocalToolResult result)
        {
            var builder = new StringBuilder();
            builder.AppendLine("UI build did not complete.");
            builder.AppendLine(string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);

            JObject details = result.RawResponse?["details"] as JObject;
            JObject doctor = details?["doctor"] as JObject;
            if (ContainsTimeout(result.Error))
            {
                builder.AppendLine("Try this next:");
                builder.AppendLine("- Run Start UI Build once more to confirm whether the Unity Editor was only temporarily busy.");
                builder.AppendLine("- Increase the Unity MCP Timeout value. Heavier projects may need 120000 to 180000 ms.");
                builder.AppendLine("- Check the Unity Console to make sure compile and import have finished before retrying.");
            }

            if (doctor != null)
            {
                List<string> nextActions = CollectStringArray(doctor["nextActions"] as JArray);
                if (nextActions.Count > 0)
                {
                    builder.AppendLine("Try this next:");
                    foreach (string action in nextActions)
                    {
                        builder.AppendLine("- " + action);
                    }
                }
            }

            if (!string.IsNullOrWhiteSpace(result.StandardError))
            {
                string missingModule = TryExtractMissingModule(result.StandardError);
                if (!string.IsNullOrWhiteSpace(missingModule))
                {
                    builder.AppendLine($"Missing Python module: {missingModule}");
                    builder.AppendLine("Try this next:");
                    builder.AppendLine("- Run Bootstrap Python Runtime first to prepare the repo-local `.venv`.");
                    builder.AppendLine("- If the problem continues, set Python Executable to an interpreter that already has the requirements installed.");
                }
            }

            return builder.ToString().Trim();
        }

        private static JObject FindDoctorCheck(JObject doctorPayload, string key)
        {
            JArray checks = doctorPayload?["checks"] as JArray;
            if (checks == null)
            {
                return null;
            }

            foreach (JToken token in checks)
            {
                if (token is JObject check && string.Equals(check.Value<string>("key"), key, StringComparison.Ordinal))
                {
                    return check;
                }
            }

            return null;
        }

        private static string DescribeDraftTemplate(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "HUD / Top Bar";
                case UnityResourceRagDraftTemplateMode.List:
                    return "List / Inventory";
                default:
                    return "Popup / Modal";
            }
        }

        private static string DescribeTemplateMode(string mode)
        {
            switch ((mode ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "hud":
                    return "HUD / Top Bar";
                case "list":
                    return "List / Inventory";
                default:
                    return "Popup / Modal";
            }
        }

        private static List<string> CollectDoctorWarnings(JArray checks)
        {
            var warnings = new List<string>();
            if (checks == null)
            {
                return warnings;
            }

            foreach (JToken token in checks)
            {
                if (token is not JObject check)
                {
                    continue;
                }

                string status = check.Value<string>("status") ?? string.Empty;
                if (status != "warn" && status != "error")
                {
                    continue;
                }

                string key = check.Value<string>("key") ?? "check";
                string summary = check.Value<string>("summary") ?? "needs attention";
                warnings.Add($"{key}: {summary}");
            }

            return warnings;
        }

        public static List<string> CollectStringArray(JArray items)
        {
            var values = new List<string>();
            if (items == null)
            {
                return values;
            }

            foreach (JToken token in items)
            {
                string value = token?.ToString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    values.Add(value);
                }
            }

            return values;
        }

        public static string DescribeReadinessLevel(UnityResourceRagReadinessLevel level)
        {
            switch (level)
            {
                case UnityResourceRagReadinessLevel.Ready:
                    return "Ready";
                case UnityResourceRagReadinessLevel.Attention:
                    return "Attention";
                default:
                    return "Blocked";
            }
        }

        private static string BuildApplySummary(JObject unityApply)
        {
            if (unityApply == null)
            {
                return "skipped";
            }

            string message = unityApply.SelectToken("response.message")?.ToString()
                ?? unityApply.SelectToken("content[0].text")?.ToString();
            return string.IsNullOrWhiteSpace(message) ? "completed" : message;
        }

        private static void AppendIfPresent(List<string> lines, string label, string value)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                lines.Add($"{label}: {value}");
            }
        }

        private static string FirstNonEmpty(params string[] values)
        {
            foreach (string value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    return value;
                }
            }

            return string.Empty;
        }

        private static string TryExtractMissingModule(string stderr)
        {
            if (string.IsNullOrWhiteSpace(stderr))
            {
                return string.Empty;
            }

            const string marker = "ModuleNotFoundError: No module named '";
            int startIndex = stderr.IndexOf(marker, StringComparison.Ordinal);
            if (startIndex < 0)
            {
                return string.Empty;
            }

            startIndex += marker.Length;
            int endIndex = stderr.IndexOf("'", startIndex, StringComparison.Ordinal);
            if (endIndex <= startIndex)
            {
                return string.Empty;
            }

            return stderr.Substring(startIndex, endIndex - startIndex);
        }

        private static bool ContainsTimeout(string value)
        {
            return !string.IsNullOrWhiteSpace(value)
                && value.IndexOf("timed out", StringComparison.OrdinalIgnoreCase) >= 0;
        }
    }
}
