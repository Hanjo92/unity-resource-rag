using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.PackageManager;
using UnityEngine;

namespace UnityResourceRag.Editor
{
    public enum UnityResourceRagAuthMode
    {
        [InspectorName("Use my Codex sign-in (Recommended)")]
        UseExistingCodexLogin = 0,

        [InspectorName("Use an API key from my environment")]
        UseApiKeyEnvironmentVariable = 1,

        [InspectorName("Stay offline with local fallback")]
        OfflineLocal = 2,
    }

    [FilePath("ProjectSettings/UnityResourceRagSettings.asset", FilePathAttribute.Location.ProjectFolder)]
    public sealed class UnityResourceRagEditorSettings : ScriptableSingleton<UnityResourceRagEditorSettings>
    {
        private const string DefaultPythonExecutable = "python3";
        private const string DefaultUnityMcpBaseUrl = "http://127.0.0.1:8080";
        private const string DefaultScreenName = "ResourceRagDraft";
        private const string DefaultGoal = "reward popup";
        private const string DefaultTitle = "Reward Unlocked";
        private const string DefaultBody = "Catalog-first popup draft";
        private const string DefaultPrimaryAction = "CLAIM";
        private const string DefaultSecondaryAction = "CLOSE";
        private const int DefaultUnityMcpTimeoutMs = 120000;

        [SerializeField] private UnityResourceRagAuthMode _authMode = UnityResourceRagAuthMode.UseExistingCodexLogin;
        [SerializeField] private string _sidecarRepoRoot = string.Empty;
        [SerializeField] private string _pythonExecutable = DefaultPythonExecutable;
        [SerializeField] private string _unityMcpBaseUrl = DefaultUnityMcpBaseUrl;
        [SerializeField] private string _codexConfigPath = string.Empty;
        [SerializeField] private string _codexAuthFile = string.Empty;
        [SerializeField] private string _providerApiKeyEnv = "OPENAI_API_KEY";
        [SerializeField] private int _unityMcpTimeoutMs = DefaultUnityMcpTimeoutMs;
        [SerializeField] private bool _applyInUnity = true;
        [SerializeField] private bool _validateBeforeApply = true;
        [SerializeField] private bool _forceReindex = false;
        [SerializeField] private string _referenceImagePath = string.Empty;
        [SerializeField] private string _goal = DefaultGoal;
        [SerializeField] private string _screenName = DefaultScreenName;
        [SerializeField] private string _title = DefaultTitle;
        [SerializeField] private string _body = DefaultBody;
        [SerializeField] private string _primaryActionLabel = DefaultPrimaryAction;
        [SerializeField] private string _secondaryActionLabel = DefaultSecondaryAction;

        public UnityResourceRagAuthMode AuthMode
        {
            get => _authMode;
            set => _authMode = value;
        }

        public string SidecarRepoRoot
        {
            get => _sidecarRepoRoot;
            set => _sidecarRepoRoot = NormalizePath(value);
        }

        public string PythonExecutable
        {
            get => string.IsNullOrWhiteSpace(_pythonExecutable) ? DefaultPythonExecutable : _pythonExecutable;
            set => _pythonExecutable = string.IsNullOrWhiteSpace(value) ? DefaultPythonExecutable : value.Trim();
        }

        public string UnityMcpBaseUrl
        {
            get => string.IsNullOrWhiteSpace(_unityMcpBaseUrl) ? DefaultUnityMcpBaseUrl : _unityMcpBaseUrl.Trim();
            set => _unityMcpBaseUrl = string.IsNullOrWhiteSpace(value) ? DefaultUnityMcpBaseUrl : value.Trim().TrimEnd('/');
        }

        public string UnityMcpRpcUrl => AppendPathSegment(UnityMcpBaseUrl, "mcp");

        public string CodexConfigPath
        {
            get => string.IsNullOrWhiteSpace(_codexConfigPath) ? DefaultCodexConfigPath() : NormalizePath(_codexConfigPath);
            set => _codexConfigPath = NormalizePath(value);
        }

        public string CodexAuthFile
        {
            get => string.IsNullOrWhiteSpace(_codexAuthFile) ? DefaultCodexAuthFilePath() : NormalizePath(_codexAuthFile);
            set => _codexAuthFile = NormalizePath(value);
        }

        public string ProviderApiKeyEnv
        {
            get => string.IsNullOrWhiteSpace(_providerApiKeyEnv) ? "OPENAI_API_KEY" : _providerApiKeyEnv.Trim();
            set => _providerApiKeyEnv = string.IsNullOrWhiteSpace(value) ? "OPENAI_API_KEY" : value.Trim();
        }

        public int UnityMcpTimeoutMs
        {
            get => _unityMcpTimeoutMs < 1000 ? DefaultUnityMcpTimeoutMs : _unityMcpTimeoutMs;
            set => _unityMcpTimeoutMs = value < 1000 ? DefaultUnityMcpTimeoutMs : value;
        }

        public bool ApplyInUnity
        {
            get => _applyInUnity;
            set => _applyInUnity = value;
        }

        public bool ValidateBeforeApply
        {
            get => _validateBeforeApply;
            set => _validateBeforeApply = value;
        }

        public bool ForceReindex
        {
            get => _forceReindex;
            set => _forceReindex = value;
        }

        public string ReferenceImagePath
        {
            get => NormalizePath(_referenceImagePath);
            set => _referenceImagePath = NormalizePath(value);
        }

        public string Goal
        {
            get => string.IsNullOrWhiteSpace(_goal) ? DefaultGoal : _goal;
            set => _goal = string.IsNullOrWhiteSpace(value) ? DefaultGoal : value.Trim();
        }

        public string ScreenName
        {
            get => string.IsNullOrWhiteSpace(_screenName) ? DefaultScreenName : _screenName.Trim();
            set => _screenName = string.IsNullOrWhiteSpace(value) ? DefaultScreenName : value.Trim();
        }

        public string Title
        {
            get => string.IsNullOrWhiteSpace(_title) ? DefaultTitle : _title;
            set => _title = string.IsNullOrWhiteSpace(value) ? DefaultTitle : value.Trim();
        }

        public string Body
        {
            get => string.IsNullOrWhiteSpace(_body) ? DefaultBody : _body;
            set => _body = string.IsNullOrWhiteSpace(value) ? DefaultBody : value.Trim();
        }

        public string PrimaryActionLabel
        {
            get => string.IsNullOrWhiteSpace(_primaryActionLabel) ? DefaultPrimaryAction : _primaryActionLabel;
            set => _primaryActionLabel = string.IsNullOrWhiteSpace(value) ? DefaultPrimaryAction : value.Trim();
        }

        public string SecondaryActionLabel
        {
            get => string.IsNullOrWhiteSpace(_secondaryActionLabel) ? DefaultSecondaryAction : _secondaryActionLabel;
            set => _secondaryActionLabel = string.IsNullOrWhiteSpace(value) ? DefaultSecondaryAction : value.Trim();
        }

        public string UnityProjectPath => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));

        public bool HasReadableCodexAuthFile => !string.IsNullOrWhiteSpace(CodexAuthFile) && File.Exists(CodexAuthFile);

        public string EffectiveConnectionPreset
        {
            get
            {
                switch (AuthMode)
                {
                    case UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable:
                        return "openai_api_key";
                    case UnityResourceRagAuthMode.OfflineLocal:
                        return "offline_local";
                    default:
                        return HasReadableCodexAuthFile ? "codex_oauth" : "recommended_auto";
                }
            }
        }

        public void EnsureDefaults()
        {
            if (string.IsNullOrWhiteSpace(SidecarRepoRoot) && TryDetectSidecarRepoRoot(out var detectedRepoRoot))
            {
                SidecarRepoRoot = detectedRepoRoot;
            }

            if (ShouldAutoDetectPythonExecutable() && TryDetectWorkingPythonExecutable(SidecarRepoRoot, out string detectedPython))
            {
                _pythonExecutable = detectedPython;
            }

            PythonExecutable = PythonExecutable;
            UnityMcpBaseUrl = UnityMcpBaseUrl;
            CodexConfigPath = CodexConfigPath;
            CodexAuthFile = CodexAuthFile;
            ProviderApiKeyEnv = ProviderApiKeyEnv;
            UnityMcpTimeoutMs = UnityMcpTimeoutMs;
            Goal = Goal;
            ScreenName = ScreenName;
            Title = Title;
            Body = Body;
            PrimaryActionLabel = PrimaryActionLabel;
            SecondaryActionLabel = SecondaryActionLabel;
        }

        public void SaveSettings()
        {
            Save(true);
        }

        public static string DefaultCodexConfigPath()
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".codex", "config.toml");
        }

        public static string DefaultCodexAuthFilePath()
        {
            string codexHome = Environment.GetEnvironmentVariable("CODEX_HOME");
            string baseDirectory = string.IsNullOrWhiteSpace(codexHome)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".codex")
                : codexHome;
            return Path.GetFullPath(Path.Combine(baseDirectory, "auth.json"));
        }

        public static bool IsSidecarRepoRoot(string candidatePath)
        {
            if (string.IsNullOrWhiteSpace(candidatePath))
            {
                return false;
            }

            string normalized = NormalizePath(candidatePath);
            if (string.IsNullOrWhiteSpace(normalized) || !Directory.Exists(normalized))
            {
                return false;
            }

            return File.Exists(Path.Combine(normalized, "requirements.txt"))
                && File.Exists(Path.Combine(normalized, "pipeline", "mcp", "server.py"))
                && File.Exists(Path.Combine(normalized, "pipeline", "mcp", "local_runner.py"));
        }

        public static bool TryDetectSidecarRepoRoot(out string repoRoot)
        {
            repoRoot = string.Empty;
            UnityEditor.PackageManager.PackageInfo packageInfo =
                UnityEditor.PackageManager.PackageInfo.FindForAssembly(Assembly.GetExecutingAssembly());
            if (packageInfo == null || string.IsNullOrWhiteSpace(packageInfo.resolvedPath))
            {
                return false;
            }

            string resolvedPath = NormalizePath(packageInfo.resolvedPath);
            string[] candidates =
            {
                Path.GetFullPath(Path.Combine(resolvedPath, "..", "..")),
                Path.GetFullPath(Path.Combine(resolvedPath, "..", "..", "..")),
                resolvedPath,
            };

            foreach (string candidate in candidates)
            {
                if (!IsSidecarRepoRoot(candidate))
                {
                    continue;
                }

                repoRoot = candidate;
                return true;
            }

            return false;
        }

        public static bool TryDetectWorkingPythonExecutable(string sidecarRepoRoot, out string executablePath)
        {
            executablePath = string.Empty;
            foreach (string candidate in EnumeratePythonCandidates(sidecarRepoRoot))
            {
                if (!CanRunSidecarImports(candidate, sidecarRepoRoot))
                {
                    continue;
                }

                executablePath = candidate;
                return true;
            }

            return false;
        }

        public static bool TryDetectBootstrapPythonExecutable(string sidecarRepoRoot, out string executablePath)
        {
            executablePath = string.Empty;
            foreach (string candidate in EnumeratePythonCandidates(sidecarRepoRoot))
            {
                if (!CanRunBasicPythonProbe(candidate, sidecarRepoRoot))
                {
                    continue;
                }

                executablePath = candidate;
                return true;
            }

            return false;
        }

        public static string GetRepositoryVenvPythonPath(string sidecarRepoRoot)
        {
            string repoRoot = NormalizePath(sidecarRepoRoot);
            if (string.IsNullOrWhiteSpace(repoRoot))
            {
                return string.Empty;
            }

            return Application.platform == RuntimePlatform.WindowsEditor
                ? NormalizePath(Path.Combine(repoRoot, ".venv", "Scripts", "python.exe"))
                : NormalizePath(Path.Combine(repoRoot, ".venv", "bin", "python"));
        }

        public static bool IsPythonReadyForSidecar(string pythonExecutable, string sidecarRepoRoot)
        {
            return CanRunSidecarImports(pythonExecutable, sidecarRepoRoot);
        }

        private static string NormalizePath(string rawPath)
        {
            if (string.IsNullOrWhiteSpace(rawPath))
            {
                return string.Empty;
            }

            try
            {
                return Path.GetFullPath(Environment.ExpandEnvironmentVariables(rawPath.Trim()));
            }
            catch
            {
                return rawPath.Trim();
            }
        }

        private static string AppendPathSegment(string baseUrl, string segment)
        {
            if (string.IsNullOrWhiteSpace(baseUrl))
            {
                return string.Empty;
            }

            return baseUrl.TrimEnd('/') + "/" + segment.TrimStart('/');
        }

        private bool ShouldAutoDetectPythonExecutable()
        {
            return string.IsNullOrWhiteSpace(_pythonExecutable)
                || string.Equals(_pythonExecutable, DefaultPythonExecutable, StringComparison.OrdinalIgnoreCase)
                || string.Equals(_pythonExecutable, "python", StringComparison.OrdinalIgnoreCase);
        }

        private static IEnumerable<string> EnumeratePythonCandidates(string sidecarRepoRoot)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string candidate in new[]
                     {
                         SafePathCombine(sidecarRepoRoot, ".venv", "bin", "python"),
                         SafePathCombine(sidecarRepoRoot, ".venv", "Scripts", "python.exe"),
                         "/opt/homebrew/Caskroom/miniforge/base/bin/python3",
                         "/opt/homebrew/bin/python3",
                         "/opt/homebrew/bin/python",
                         "/usr/local/bin/python3",
                         "/usr/local/bin/python",
                         "python3",
                         "python",
                     })
            {
                if (string.IsNullOrWhiteSpace(candidate))
                {
                    continue;
                }

                string normalized = candidate;
                if (candidate.Contains(Path.DirectorySeparatorChar.ToString()) || candidate.Contains(Path.AltDirectorySeparatorChar.ToString()))
                {
                    normalized = NormalizePath(candidate);
                    if (!File.Exists(normalized))
                    {
                        continue;
                    }
                }

                if (seen.Add(normalized))
                {
                    yield return normalized;
                }
            }
        }

        private static bool CanRunSidecarImports(string pythonExecutable, string sidecarRepoRoot)
        {
            if (string.IsNullOrWhiteSpace(pythonExecutable))
            {
                return false;
            }

            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = pythonExecutable,
                    Arguments = "-c \"import pydantic\"",
                    WorkingDirectory = string.IsNullOrWhiteSpace(sidecarRepoRoot) ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) : sidecarRepoRoot,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };

                using Process process = Process.Start(startInfo);
                if (process == null)
                {
                    return false;
                }

                if (!process.WaitForExit(3000))
                {
                    try
                    {
                        process.Kill();
                    }
                    catch
                    {
                        // Ignore cleanup failure for timed-out probe.
                    }

                    return false;
                }

                return process.ExitCode == 0;
            }
            catch
            {
                return false;
            }
        }

        private static bool CanRunBasicPythonProbe(string pythonExecutable, string sidecarRepoRoot)
        {
            if (string.IsNullOrWhiteSpace(pythonExecutable))
            {
                return false;
            }

            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = pythonExecutable,
                    Arguments = "-c \"import sys; print(sys.executable)\"",
                    WorkingDirectory = string.IsNullOrWhiteSpace(sidecarRepoRoot) ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) : sidecarRepoRoot,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };

                using Process process = Process.Start(startInfo);
                if (process == null)
                {
                    return false;
                }

                if (!process.WaitForExit(3000))
                {
                    try
                    {
                        process.Kill();
                    }
                    catch
                    {
                        // Ignore cleanup failure for timed-out probe.
                    }

                    return false;
                }

                return process.ExitCode == 0;
            }
            catch
            {
                return false;
            }
        }

        private static string SafePathCombine(string root, params string[] parts)
        {
            if (string.IsNullOrWhiteSpace(root))
            {
                return string.Empty;
            }

            try
            {
                var allParts = new List<string> { root };
                allParts.AddRange(parts);
                return Path.Combine(allParts.ToArray());
            }
            catch
            {
                return string.Empty;
            }
        }
    }
}
