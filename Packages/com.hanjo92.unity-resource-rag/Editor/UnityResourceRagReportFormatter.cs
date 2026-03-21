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
                    ? "Readiness check를 마쳤습니다."
                    : "현재 설정 기준 readiness 상태를 정리했습니다.",
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
                return "Case export 결과가 없습니다.";
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
                lines.Add("- case-report.md에 실제 화면 품질 메모를 보강한 뒤 GitHub issue나 release follow-up에 붙입니다.");
                lines.Add("- 이후 같은 화면에서 수정 전/후 결과를 비교할 때 같은 case folder를 기준 artifact로 씁니다.");
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
                return "결과 스크린샷을 캡처하지 못했습니다.\n" + (string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);
            }

            JObject payload = result.Payload;
            string screenshotPath = payload?.Value<string>("capturedPath") ?? "(not found)";
            string relativePath = payload?.Value<string>("capturedPathRelative") ?? string.Empty;
            var lines = new List<string>
            {
                "결과 스크린샷을 저장했습니다.",
                $"Screenshot: {screenshotPath}",
            };
            if (!string.IsNullOrWhiteSpace(relativePath))
            {
                lines.Add($"Unity Asset Path: {relativePath}");
            }

            lines.Add("Next:");
            lines.Add("- 캡처 결과를 보고 spacing, asset choice, hierarchy를 빠르게 점검합니다.");
            lines.Add("- reference build였다면 같은 창에서 Repair Handoff를 실행할 수 있습니다.");
            return string.Join("\n", lines);
        }

        public static string FormatRepairReport(UnityResourceRagLocalToolResult result)
        {
            if (!result.Success)
            {
                return "Repair handoff를 만들지 못했습니다.\n" + (string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);
            }

            JObject payload = result.Payload;
            var lines = new List<string>
            {
                "Repair handoff를 만들었습니다.",
            };

            AppendIfPresent(lines, "Verification Report", payload?.Value<string>("verificationReport"));
            AppendIfPresent(lines, "Repair Handoff", payload?.Value<string>("repairHandoff"));
            AppendIfPresent(lines, "Workflow Report", payload?.Value<string>("workflowReport"));

            if ((payload?.Value<bool?>("hasErrors") ?? false))
            {
                lines.Add("Attention:");
                lines.Add("- verification workflow 안에 일부 에러가 있습니다. report 파일을 먼저 확인해 주세요.");
            }
            else
            {
                lines.Add("Next:");
                lines.Add("- repair handoff를 기준으로 작은 수정부터 적용합니다.");
                lines.Add("- 수정 후에는 다시 캡처해서 비교 결과를 확인합니다.");
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
                    Summary = "one-click build에 필요한 full unity-resource-rag checkout을 찾았습니다.",
                    NextStep = settings.SidecarRepoRoot,
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Sidecar Repo",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "현재 경로만으로는 Python sidecar를 실행할 수 없습니다.",
                NextStep = "Sidecar Repo Root에 full unity-resource-rag checkout 경로를 지정해 주세요.",
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
                    Summary = "repo-local Python runtime이 준비되어 있습니다.",
                    NextStep = repoVenvPython,
                };
            }

            if (UnityResourceRagEditorSettings.TryDetectWorkingPythonExecutable(repoRoot, out string detectedPython))
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Python Runtime",
                    Level = UnityResourceRagReadinessLevel.Attention,
                    Summary = "작동 가능한 Python은 찾았지만 repo-local runtime은 아직 고정되지 않았습니다.",
                    NextStep = $"Bootstrap Python Runtime을 실행하거나 `{detectedPython}` 를 그대로 사용할 수 있습니다.",
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Python Runtime",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "sidecar dependency를 로드할 수 있는 Python runtime이 아직 없습니다.",
                NextStep = "Bootstrap Python Runtime을 실행해 `.venv` 와 requirements를 준비해 주세요.",
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
                            Title = "Provider Login",
                            Level = UnityResourceRagReadinessLevel.Ready,
                            Summary = "기존 Codex 로그인 정보를 그대로 재사용할 수 있습니다.",
                            NextStep = settings.CodexAuthFile,
                        };
                    }

                    return new UnityResourceRagReadinessItem
                    {
                        Title = "Provider Login",
                        Level = UnityResourceRagReadinessLevel.Attention,
                        Summary = "Codex 로그인 파일을 아직 찾지 못했습니다.",
                        NextStep = "Codex에 로그인했는지 확인하거나 Offline local로 먼저 테스트해 보세요.",
                    };
                case UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable:
                    if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(settings.ProviderApiKeyEnv)))
                    {
                        return new UnityResourceRagReadinessItem
                        {
                            Title = "Provider Login",
                            Level = UnityResourceRagReadinessLevel.Ready,
                            Summary = $"API key 환경 변수 `{settings.ProviderApiKeyEnv}` 를 사용할 준비가 됐습니다.",
                            NextStep = "이 모드에서는 API key env가 우선 사용됩니다.",
                        };
                    }

                    return new UnityResourceRagReadinessItem
                    {
                        Title = "Provider Login",
                        Level = UnityResourceRagReadinessLevel.Attention,
                        Summary = $"API key 환경 변수 `{settings.ProviderApiKeyEnv}` 가 비어 있습니다.",
                        NextStep = "환경 변수를 채우거나 Use existing Codex login으로 바꿔 보세요.",
                    };
                default:
                    return new UnityResourceRagReadinessItem
                    {
                        Title = "Provider Login",
                        Level = UnityResourceRagReadinessLevel.Ready,
                        Summary = "Offline local fallback으로 테스트를 진행할 수 있습니다.",
                        NextStep = "인터넷 연결 없이도 catalog-first 초안과 apply 흐름을 확인할 수 있습니다.",
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
                    Summary = "아직 readiness 확인을 실행하지 않았습니다.",
                    NextStep = "Refresh Readiness를 눌러 Unity MCP 연결 상태를 확인해 주세요.",
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
                    Summary = "Unity Editor와 필요한 build tool 연결이 준비됐습니다.",
                    NextStep = settings.UnityMcpRpcUrl,
                };
            }

            if (hasMissingTools || status == "error")
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Blocked,
                    Summary = "Unity Editor는 보이지만 필요한 build tool이 아직 전부 준비되진 않았습니다.",
                    NextStep = "Quick Setup을 다시 실행하고, Local HTTP Server와 custom tool 노출 상태를 확인해 주세요.",
                };
            }

            if (hasMissingResources)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Unity Editor Connection",
                    Level = UnityResourceRagReadinessLevel.Attention,
                    Summary = "UI build는 가능한 상태지만 catalog/resource 정보는 일부만 보입니다.",
                    NextStep = "대부분의 build는 계속 진행할 수 있습니다. raw catalog browsing이 필요할 때만 추가 확인해 주세요.",
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Unity Editor Connection",
                Level = UnityResourceRagReadinessLevel.Attention,
                Summary = "Unity Editor readiness에 확인이 필요한 항목이 있습니다.",
                NextStep = FirstNonEmpty(
                    (check["nextActions"] as JArray)?.First?.ToString(),
                    "Quick Setup 또는 Refresh Readiness를 다시 실행해 주세요."),
            };
        }

        private static UnityResourceRagReadinessItem BuildBuildInputItem(UnityResourceRagEditorSettings settings, JObject doctorPayload)
        {
            JObject catalogCheck = FindDoctorCheck(doctorPayload, "catalog");
            bool hasReference = !string.IsNullOrWhiteSpace(settings.ReferenceImagePath) && File.Exists(settings.ReferenceImagePath);
            bool hasDraftInput = !string.IsNullOrWhiteSpace(settings.Goal) || !string.IsNullOrWhiteSpace(settings.Title) || !string.IsNullOrWhiteSpace(settings.Body);
            bool catalogReady = string.Equals(catalogCheck?.Value<string>("status"), "ok", StringComparison.OrdinalIgnoreCase);

            if (hasReference)
            {
                return new UnityResourceRagReadinessItem
                {
                    Title = "Build Input",
                    Level = UnityResourceRagReadinessLevel.Ready,
                    Summary = catalogReady
                        ? "reference image와 project catalog가 준비돼 있습니다."
                        : "reference image는 준비됐고, catalog는 필요하면 build 중에 다시 확인합니다.",
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
                        ? "catalog-first draft를 시작할 입력이 준비돼 있습니다."
                        : "goal/title/body는 준비됐고, catalog가 없으면 첫 build에서 생성합니다.",
                    NextStep = string.IsNullOrWhiteSpace(settings.Goal) ? settings.Title : settings.Goal,
                };
            }

            return new UnityResourceRagReadinessItem
            {
                Title = "Build Input",
                Level = UnityResourceRagReadinessLevel.Blocked,
                Summary = "reference image 또는 catalog-first draft 입력이 필요합니다.",
                NextStep = "Reference Image를 넣거나 Goal/Title/Body를 채워 주세요.",
            };
        }

        private static string FormatSuccessfulBuildReport(UnityResourceRagLocalToolResult result)
        {
            JObject payload = result.Payload;
            if (payload == null)
            {
                return string.IsNullOrWhiteSpace(result.Summary) ? "UI build를 마쳤습니다." : result.Summary;
            }

            string routeLabel = ExtractRouteLabel(payload);
            string blueprintPath = ExtractBlueprintPath(payload);
            string handoffPath = ExtractHandoffPath(payload);
            string applySummary = BuildApplySummary(payload.SelectToken("execution.unityApply") as JObject);

            var lines = new List<string>
            {
                "UI build를 마쳤습니다.",
                $"Flow: {routeLabel}",
            };

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
            builder.AppendLine("UI build를 완료하지 못했습니다.");
            builder.AppendLine(string.IsNullOrWhiteSpace(result.Error) ? "Unknown error." : result.Error);

            JObject details = result.RawResponse?["details"] as JObject;
            JObject doctor = details?["doctor"] as JObject;
            if (ContainsTimeout(result.Error))
            {
                builder.AppendLine("Try this next:");
                builder.AppendLine("- Start UI Build를 한 번 더 실행해 일시적인 Unity Editor busy 상태였는지 확인합니다.");
                builder.AppendLine("- Unity MCP Timeout 값을 더 크게 올립니다. 무거운 프로젝트는 120000~180000ms가 더 안전할 수 있습니다.");
                builder.AppendLine("- Unity Console에서 compile/import가 끝났는지 확인한 뒤 다시 시도합니다.");
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
                    builder.AppendLine("- Bootstrap Python Runtime을 먼저 실행해 repo-local `.venv` 를 준비합니다.");
                    builder.AppendLine("- 그래도 같으면 Python Executable에 requirements가 설치된 interpreter 경로를 직접 넣습니다.");
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
