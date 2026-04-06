using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagLocalToolResult
    {
        public bool Success { get; set; }
        public string Summary { get; set; } = string.Empty;
        public string Error { get; set; } = string.Empty;
        public string StandardOutput { get; set; } = string.Empty;
        public string StandardError { get; set; } = string.Empty;
        public JObject Payload { get; set; }
        public JObject RawResponse { get; set; }
    }

    public static class UnityResourceRagLocalRunner
    {
        private sealed class PreparedToolRun
        {
            public string PythonExecutable { get; set; } = string.Empty;
            public string SidecarRepoRoot { get; set; } = string.Empty;
            public string ToolName { get; set; } = string.Empty;
            public string PayloadFile { get; set; } = string.Empty;
        }

        public static UnityResourceRagLocalToolResult RunDoctor(UnityResourceRagEditorSettings settings)
        {
            settings.EnsureDefaults();
            return RunTool(settings, "doctor", BuildDoctorPayload(settings));
        }

        public static UnityResourceRagLocalToolResult RunStartUiBuild(UnityResourceRagEditorSettings settings)
        {
            settings.EnsureDefaults();
            Dictionary<string, object> payload = BuildStartUiBuildPayload(settings);
            return RunTool(settings, "start_ui_build", payload);
        }

        public static bool TryRunDoctorAsync(UnityResourceRagEditorSettings settings, Action<UnityResourceRagLocalToolResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            return TryRunToolAsync(settings, "doctor", BuildDoctorPayload(settings), onComplete, out error);
        }

        public static bool TryRunStartUiBuildAsync(UnityResourceRagEditorSettings settings, Action<UnityResourceRagLocalToolResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            Dictionary<string, object> payload = BuildStartUiBuildPayload(settings);
            return TryRunToolAsync(settings, "start_ui_build", payload, onComplete, out error);
        }

        public static bool TryRunCaptureResultAsync(UnityResourceRagEditorSettings settings, JObject buildPayload, Action<UnityResourceRagLocalToolResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            return TryRunToolAsync(settings, "capture_result", BuildCaptureResultPayload(settings, buildPayload), onComplete, out error);
        }

        public static bool TryRunVerificationRepairAsync(UnityResourceRagEditorSettings settings, string capturedImagePath, string resolvedBlueprintPath, string outputDirectory, Action<UnityResourceRagLocalToolResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            return TryRunToolAsync(settings, "run_verification_repair_loop", BuildVerificationRepairPayload(settings, capturedImagePath, resolvedBlueprintPath, outputDirectory), onComplete, out error);
        }

        public static bool TryRunToolAsync(UnityResourceRagEditorSettings settings, string toolName, Dictionary<string, object> payload, Action<UnityResourceRagLocalToolResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            PreparedToolRun preparedRun = PrepareToolRun(settings, toolName, payload, out UnityResourceRagLocalToolResult immediateFailure);
            if (preparedRun == null)
            {
                error = immediateFailure?.Error ?? $"Failed to start tool `{toolName}`.";
                return false;
            }

            error = string.Empty;
            Task.Run(() =>
            {
                UnityResourceRagLocalToolResult result = ExecutePreparedToolRun(preparedRun);
                EditorApplication.delayCall += () => onComplete?.Invoke(result);
            });
            return true;
        }

        public static Dictionary<string, object> BuildDoctorPayload(UnityResourceRagEditorSettings settings)
        {
            var payload = new Dictionary<string, object>
            {
                ["unity_project_path"] = settings.UnityProjectPath,
                ["connection_preset"] = settings.EffectiveConnectionPreset,
                ["provider_api_key_env"] = settings.ProviderApiKeyEnv,
                ["unity_mcp_url"] = settings.UnityMcpRpcUrl,
                ["unity_mcp_timeout_ms"] = settings.UnityMcpTimeoutMs,
            };

            if (settings.AuthMode == UnityResourceRagAuthMode.UseExistingCodexLogin && settings.HasReadableCodexAuthFile)
            {
                payload["codex_auth_file"] = settings.CodexAuthFile;
            }

            if (!string.IsNullOrWhiteSpace(settings.ReferenceImagePath))
            {
                payload["reference_image"] = settings.ReferenceImagePath;
            }

            return payload;
        }

        public static Dictionary<string, object> BuildStartUiBuildPayload(UnityResourceRagEditorSettings settings, bool runDoctor = true, bool requireDoctorOk = true)
        {
            var payload = new Dictionary<string, object>
            {
                ["unity_project_path"] = settings.UnityProjectPath,
                ["connection_preset"] = settings.EffectiveConnectionPreset,
                ["provider_api_key_env"] = settings.ProviderApiKeyEnv,
                ["unity_mcp_url"] = settings.UnityMcpRpcUrl,
                ["unity_mcp_timeout_ms"] = settings.UnityMcpTimeoutMs,
                ["apply_in_unity"] = settings.ApplyInUnity,
                ["validate_before_apply"] = settings.ValidateBeforeApply,
                ["force_reindex"] = settings.ForceReindex,
                ["run_doctor"] = runDoctor,
                ["require_doctor_ok"] = requireDoctorOk,
            };

            if (settings.AuthMode == UnityResourceRagAuthMode.UseExistingCodexLogin && settings.HasReadableCodexAuthFile)
            {
                payload["codex_auth_file"] = settings.CodexAuthFile;
            }

            if (!string.IsNullOrWhiteSpace(settings.ReferenceImagePath))
            {
                payload["image"] = settings.ReferenceImagePath;
            }
            else
            {
                payload["goal"] = settings.Goal;
                payload["template_mode"] = settings.EffectiveTemplateMode;
                payload["screen_name"] = settings.ScreenName;
                payload["title"] = settings.Title;
                payload["body"] = settings.Body;
                payload["primary_action_label"] = settings.PrimaryActionLabel;
                payload["secondary_action_label"] = settings.SecondaryActionLabel;
            }

            return payload;
        }

        public static Dictionary<string, object> BuildCaptureResultPayload(UnityResourceRagEditorSettings settings, JObject buildPayload)
        {
            var payload = new Dictionary<string, object>
            {
                ["unity_project_path"] = settings.UnityProjectPath,
                ["unity_mcp_url"] = settings.UnityMcpRpcUrl,
                ["unity_mcp_timeout_ms"] = settings.UnityMcpTimeoutMs,
                ["include_image"] = false,
                ["action"] = "screenshot",
                ["capture_source"] = "scene_view",
            };

            JObject verifyRequest = UnityResourceRagReportFormatter.ExtractVerificationRequest(buildPayload);
            if (verifyRequest != null)
            {
                payload["verify_request"] = verifyRequest;
                return payload;
            }

            string viewTarget = UnityResourceRagReportFormatter.ExtractVerifyTarget(buildPayload);
            if (!string.IsNullOrWhiteSpace(viewTarget))
            {
                payload["view_target"] = viewTarget;
            }

            return payload;
        }

        public static Dictionary<string, object> BuildVerificationRepairPayload(UnityResourceRagEditorSettings settings, string capturedImagePath, string resolvedBlueprintPath, string outputDirectory)
        {
            var payload = new Dictionary<string, object>
            {
                ["reference_image"] = settings.ReferenceImagePath,
                ["captured_image"] = capturedImagePath,
            };

            if (!string.IsNullOrWhiteSpace(resolvedBlueprintPath))
            {
                payload["resolved_blueprint"] = resolvedBlueprintPath;
            }

            if (!string.IsNullOrWhiteSpace(outputDirectory))
            {
                payload["output_dir"] = outputDirectory;
            }

            return payload;
        }

        public static UnityResourceRagLocalToolResult RunTool(UnityResourceRagEditorSettings settings, string toolName, Dictionary<string, object> payload)
        {
            PreparedToolRun preparedRun = PrepareToolRun(settings, toolName, payload, out UnityResourceRagLocalToolResult immediateFailure);
            return preparedRun != null ? ExecutePreparedToolRun(preparedRun) : immediateFailure;
        }

        private static PreparedToolRun PrepareToolRun(UnityResourceRagEditorSettings settings, string toolName, Dictionary<string, object> payload, out UnityResourceRagLocalToolResult immediateFailure)
        {
            immediateFailure = null;
            if (!UnityResourceRagEditorSettings.IsSidecarRuntimeRoot(settings.SidecarRepoRoot))
            {
                immediateFailure = new UnityResourceRagLocalToolResult
                {
                    Error = "The sidecar runtime root is not valid. Set it to a portable sidecar bundle or a full unity-resource-rag checkout path.",
                };
                return null;
            }

            string runnerPath = Path.Combine(settings.SidecarRepoRoot, "pipeline", "mcp", "local_runner.py");
            if (!File.Exists(runnerPath))
            {
                immediateFailure = new UnityResourceRagLocalToolResult
                {
                    Error = $"The local runner could not be found: {runnerPath}",
                };
                return null;
            }

            if (!UnityResourceRagEditorSettings.TryDetectWorkingPythonExecutable(settings.SidecarRepoRoot, out string detectedPython))
            {
                immediateFailure = new UnityResourceRagLocalToolResult
                {
                    Error = "No Python command that can load the sidecar requirements was found. Point Python Command to an interpreter where `pip install -r requirements.txt` has already been run.",
                };
                return null;
            }

            if (UnityResourceRagEditorSettings.IsGenericPythonCommand(settings.PythonExecutable))
            {
                settings.PythonExecutable = detectedPython;
                settings.SaveSettings();
            }

            string payloadFile = Path.GetTempFileName();
            try
            {
                File.WriteAllText(payloadFile, JsonConvert.SerializeObject(payload, Formatting.None));
            }
            catch (Exception ex)
            {
                immediateFailure = new UnityResourceRagLocalToolResult
                {
                    Error = ex.Message,
                };
                try
                {
                    File.Delete(payloadFile);
                }
                catch
                {
                    // Ignore temp-file cleanup failures.
                }
                return null;
            }

            return new PreparedToolRun
            {
                PythonExecutable = settings.PythonExecutable,
                SidecarRepoRoot = settings.SidecarRepoRoot,
                ToolName = toolName,
                PayloadFile = payloadFile,
            };
        }

        private static UnityResourceRagLocalToolResult ExecutePreparedToolRun(PreparedToolRun preparedRun)
        {
            try
            {
                ProcessStartInfo startInfo = UnityResourceRagEditorSettings.CreateCommandStartInfo(
                    preparedRun.PythonExecutable,
                    preparedRun.SidecarRepoRoot,
                    new[] { "-m", "pipeline.mcp.local_runner", preparedRun.ToolName, "--payload-file", preparedRun.PayloadFile });
                startInfo.RedirectStandardOutput = true;
                startInfo.RedirectStandardError = true;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;

                using var process = Process.Start(startInfo);
                if (process == null)
                {
                    return new UnityResourceRagLocalToolResult
                    {
                        Error = "Failed to start the Python process.",
                    };
                }

                Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
                Task<string> stderrTask = process.StandardError.ReadToEndAsync();
                if (!process.WaitForExit(600000))
                {
                    try
                    {
                        process.Kill();
                    }
                    catch
                    {
                        // Ignore cleanup failures for a timed-out child process.
                    }

                    return new UnityResourceRagLocalToolResult
                    {
                        StandardOutput = ReadTaskResult(stdoutTask),
                        StandardError = ReadTaskResult(stderrTask),
                        Error = "Python runner timed out after 10 minutes.",
                    };
                }

                string stdout = ReadTaskResult(stdoutTask);
                string stderr = ReadTaskResult(stderrTask);
                var result = new UnityResourceRagLocalToolResult
                {
                    StandardOutput = stdout,
                    StandardError = stderr,
                };

                if (string.IsNullOrWhiteSpace(stdout))
                {
                    result.Error = string.IsNullOrWhiteSpace(stderr)
                        ? "Python runner returned no output."
                        : stderr.Trim();
                    return result;
                }

                JObject response;
                try
                {
                    response = JObject.Parse(stdout);
                }
                catch (JsonException)
                {
                    result.Error = "Python runner returned non-JSON output.";
                    return result;
                }

                result.RawResponse = response;
                result.Success = response.Value<bool?>("ok") ?? process.ExitCode == 0;
                result.Error = response.Value<string>("error") ?? string.Empty;
                result.Payload = response["payload"] as JObject;
                result.Summary = BuildSummary(result.Payload);

                if (!result.Success && string.IsNullOrWhiteSpace(result.Error))
                {
                    result.Error = process.ExitCode == 0 ? "Tool execution failed." : $"Tool execution failed with exit code {process.ExitCode}.";
                }

                return result;
            }
            catch (Exception ex)
            {
                return new UnityResourceRagLocalToolResult
                {
                    Error = ex.Message,
                };
            }
            finally
            {
                try
                {
                    File.Delete(preparedRun.PayloadFile);
                }
                catch
                {
                    // Ignore temp-file cleanup failures.
                }
            }
        }

        private static string BuildSummary(JObject payload)
        {
            if (payload == null)
            {
                return "The build result payload is missing.";
            }

            string selectedPath = payload.Value<string>("selectedPath") ?? "unknown";
            string overallStatus = payload.SelectToken("doctor.overallStatus")?.ToString() ?? "unknown";
            string blueprintPath =
                payload.SelectToken("execution.draftBlueprint")?.ToString()
                ?? payload.SelectToken("execution.workflow.resolvedBlueprint")?.ToString()
                ?? payload.SelectToken("execution.handoffBundlePath")?.ToString()
                ?? string.Empty;

            string routeLabel = selectedPath == "reference_first_pass"
                ? "reference-first"
                : selectedPath == "catalog_draft"
                    ? "catalog-first"
                    : selectedPath;

            if (string.IsNullOrWhiteSpace(blueprintPath))
            {
                return $"Path: {routeLabel} / doctor: {overallStatus}";
            }

            return $"Path: {routeLabel} / doctor: {overallStatus} / blueprint: {blueprintPath}";
        }

        private static string ReadTaskResult(Task<string> task)
        {
            try
            {
                return task.GetAwaiter().GetResult();
            }
            catch
            {
                return string.Empty;
            }
        }
    }
}
