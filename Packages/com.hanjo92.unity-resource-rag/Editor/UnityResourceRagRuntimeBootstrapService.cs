using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using UnityEditor;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagRuntimeBootstrapResult
    {
        public bool Success => Errors.Count == 0;
        public List<string> Steps { get; } = new List<string>();
        public List<string> Warnings { get; } = new List<string>();
        public List<string> Errors { get; } = new List<string>();
        public string Summary { get; set; } = string.Empty;
        public string RecommendedPythonExecutable { get; set; } = string.Empty;
        public string StandardOutput { get; set; } = string.Empty;
        public string StandardError { get; set; } = string.Empty;
    }

    public static class UnityResourceRagRuntimeBootstrapService
    {
        private const int BootstrapTimeoutMs = 20 * 60 * 1000;

        public static bool TryRunAsync(UnityResourceRagEditorSettings settings, Action<UnityResourceRagRuntimeBootstrapResult> onComplete, out string error)
        {
            settings.EnsureDefaults();
            if (!UnityResourceRagEditorSettings.IsSidecarRepoRoot(settings.SidecarRepoRoot))
            {
                error = "A full unity-resource-rag checkout path is required. Set Sidecar Repo Root first.";
                return false;
            }

            if (!UnityResourceRagEditorSettings.TryDetectBootstrapPythonExecutable(settings.SidecarRepoRoot, out string bootstrapPython))
            {
                error = "No base Python interpreter was found. Make sure Python 3 is installed, then try again.";
                return false;
            }

            error = string.Empty;
            Task.Run(() =>
            {
                UnityResourceRagRuntimeBootstrapResult result = Run(settings, bootstrapPython);
                EditorApplication.delayCall += () => onComplete?.Invoke(result);
            });
            return true;
        }

        private static UnityResourceRagRuntimeBootstrapResult Run(UnityResourceRagEditorSettings settings, string bootstrapPython)
        {
            var result = new UnityResourceRagRuntimeBootstrapResult();
            string repoRoot = settings.SidecarRepoRoot;
            string requirementsPath = Path.Combine(repoRoot, "requirements.txt");
            string venvPython = UnityResourceRagEditorSettings.GetRepositoryVenvPythonPath(repoRoot);
            result.RecommendedPythonExecutable = venvPython;

            result.Steps.Add($"Bootstrap base Python: {bootstrapPython}");
            result.Steps.Add($"Repo-local runtime target: {venvPython}");

            if (string.IsNullOrWhiteSpace(venvPython))
            {
                result.Errors.Add("Could not resolve the repo-local `.venv` path.");
                result.Summary = BuildSummary(result);
                return result;
            }

            if (UnityResourceRagEditorSettings.IsPythonReadyForSidecar(venvPython, repoRoot))
            {
                settings.PythonExecutable = venvPython;
                settings.SaveSettings();
                result.Steps.Add("Found an existing ready-to-use repo-local Python runtime.");
                result.Summary = BuildSummary(result);
                return result;
            }

            string venvDirectory = Path.GetDirectoryName(venvPython) ?? string.Empty;
            if (!File.Exists(venvPython))
            {
                ProcessCommandResult createVenv = RunProcess(
                    bootstrapPython,
                    $"-m venv {Quote(Path.Combine(repoRoot, ".venv"))}",
                    repoRoot,
                    BootstrapTimeoutMs);
                AppendCommandResult(result, createVenv, "Created the repo-local `.venv`.");
                if (!createVenv.Success)
                {
                    result.Summary = BuildSummary(result);
                    return result;
                }
            }
            else
            {
                result.Warnings.Add("Reusing the existing `.venv` and refreshing its dependencies.");
            }

            if (!File.Exists(requirementsPath))
            {
                result.Errors.Add($"Could not find requirements.txt: {requirementsPath}");
                result.Summary = BuildSummary(result);
                return result;
            }

            if (!Directory.Exists(venvDirectory))
            {
                result.Errors.Add("The repo-local Python runtime was not created.");
                result.Summary = BuildSummary(result);
                return result;
            }

            ProcessCommandResult installRequirements = RunProcess(
                venvPython,
                $"-m pip install -r {Quote(requirementsPath)}",
                repoRoot,
                BootstrapTimeoutMs);
            AppendCommandResult(result, installRequirements, "Installed the requirements into the repo-local Python runtime.");
            if (!installRequirements.Success)
            {
                result.Summary = BuildSummary(result);
                return result;
            }

            if (!UnityResourceRagEditorSettings.IsPythonReadyForSidecar(venvPython, repoRoot))
            {
                result.Errors.Add("Sidecar imports still could not be verified after bootstrap.");
                result.Summary = BuildSummary(result);
                return result;
            }

            settings.PythonExecutable = venvPython;
            settings.SaveSettings();
            result.Steps.Add("Saved the repo-local Python runtime as the default interpreter for Unity Resource RAG.");
            result.Summary = BuildSummary(result);
            return result;
        }

        private static void AppendCommandResult(UnityResourceRagRuntimeBootstrapResult result, ProcessCommandResult commandResult, string successMessage)
        {
            if (!string.IsNullOrWhiteSpace(commandResult.StandardOutput))
            {
                result.StandardOutput = AppendBlock(result.StandardOutput, commandResult.StandardOutput);
            }

            if (!string.IsNullOrWhiteSpace(commandResult.StandardError))
            {
                result.StandardError = AppendBlock(result.StandardError, commandResult.StandardError);
            }

            if (commandResult.Success)
            {
                result.Steps.Add(successMessage);
            }
            else
            {
                result.Errors.Add(commandResult.ErrorMessage);
            }
        }

        private static string AppendBlock(string original, string next)
        {
            if (string.IsNullOrWhiteSpace(original))
            {
                return next?.Trim() ?? string.Empty;
            }

            return original.Trim() + "\n" + (next?.Trim() ?? string.Empty);
        }

        private static string BuildSummary(UnityResourceRagRuntimeBootstrapResult result)
        {
            if (result.Success)
            {
                return "Python runtime bootstrap completed successfully.";
            }

            return $"Python runtime bootstrap failed with {result.Errors.Count} error(s).";
        }

        private static ProcessCommandResult RunProcess(string fileName, string arguments, string workingDirectory, int timeoutMs)
        {
            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = fileName,
                    Arguments = arguments,
                    WorkingDirectory = workingDirectory,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };

                using var process = Process.Start(startInfo);
                if (process == null)
                {
                    return ProcessCommandResult.Failed("Failed to start the Python bootstrap process.");
                }

                Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
                Task<string> stderrTask = process.StandardError.ReadToEndAsync();
                if (!process.WaitForExit(timeoutMs))
                {
                    try
                    {
                        process.Kill();
                    }
                    catch
                    {
                        // Ignore cleanup failure for timed-out child process.
                    }

                    return ProcessCommandResult.Failed(
                        $"Command timed out after {timeoutMs / 1000} seconds.",
                        ReadTaskResult(stdoutTask),
                        ReadTaskResult(stderrTask));
                }

                string stdout = ReadTaskResult(stdoutTask);
                string stderr = ReadTaskResult(stderrTask);
                if (process.ExitCode != 0)
                {
                    return ProcessCommandResult.Failed(
                        string.IsNullOrWhiteSpace(stderr)
                            ? $"Command failed with exit code {process.ExitCode}."
                            : stderr.Trim(),
                        stdout,
                        stderr);
                }

                return ProcessCommandResult.Succeeded(stdout, stderr);
            }
            catch (Exception ex)
            {
                return ProcessCommandResult.Failed(ex.Message);
            }
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
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

        private readonly struct ProcessCommandResult
        {
            private ProcessCommandResult(bool success, string errorMessage, string standardOutput, string standardError)
            {
                Success = success;
                ErrorMessage = errorMessage;
                StandardOutput = standardOutput;
                StandardError = standardError;
            }

            public bool Success { get; }
            public string ErrorMessage { get; }
            public string StandardOutput { get; }
            public string StandardError { get; }

            public static ProcessCommandResult Succeeded(string standardOutput, string standardError)
            {
                return new ProcessCommandResult(true, string.Empty, standardOutput, standardError);
            }

            public static ProcessCommandResult Failed(string errorMessage, string standardOutput = "", string standardError = "")
            {
                return new ProcessCommandResult(false, errorMessage, standardOutput, standardError);
            }
        }
    }
}
