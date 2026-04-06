using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
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

    public enum UnityResourceRagDraftTemplateMode
    {
        [InspectorName("Popup / Modal")]
        Popup = 0,

        [InspectorName("HUD / Top Bar")]
        Hud = 1,

        [InspectorName("List / Inventory")]
        List = 2,
    }

    [FilePath("ProjectSettings/UnityResourceRagSettings.asset", FilePathAttribute.Location.ProjectFolder)]
    public sealed class UnityResourceRagEditorSettings : ScriptableSingleton<UnityResourceRagEditorSettings>
    {
        private const string LegacyDefaultPythonExecutable = "python3";
        private const string DefaultUnityMcpBaseUrl = "http://127.0.0.1:8080";
        private const int DefaultUnityMcpTimeoutMs = 120000;
        private const string SidecarBundleManifestFileName = "unity-resource-rag-sidecar.json";
        private static readonly Regex CommandTokenRegex = new Regex("\"([^\"]*)\"|(\\S+)", RegexOptions.Compiled);

        [SerializeField] private UnityResourceRagAuthMode _authMode = UnityResourceRagAuthMode.UseExistingCodexLogin;
        [SerializeField] private UnityResourceRagDraftTemplateMode _draftTemplateMode = UnityResourceRagDraftTemplateMode.Popup;
        [SerializeField] private string _sidecarRepoRoot = string.Empty;
        [SerializeField] private string _pythonExecutable = string.Empty;
        [SerializeField] private string _unityMcpBaseUrl = DefaultUnityMcpBaseUrl;
        [SerializeField] private string _codexConfigPath = string.Empty;
        [SerializeField] private string _codexAuthFile = string.Empty;
        [SerializeField] private string _providerApiKeyEnv = "OPENAI_API_KEY";
        [SerializeField] private int _unityMcpTimeoutMs = DefaultUnityMcpTimeoutMs;
        [SerializeField] private bool _applyInUnity = true;
        [SerializeField] private bool _validateBeforeApply = true;
        [SerializeField] private bool _forceReindex = false;
        [SerializeField] private string _referenceImagePath = string.Empty;
        [SerializeField] private string _goal = "reward popup";
        [SerializeField] private string _screenName = "ResourceRagDraft";
        [SerializeField] private string _title = "Reward Unlocked";
        [SerializeField] private string _body = "Catalog-first popup draft";
        [SerializeField] private string _primaryActionLabel = "CLAIM";
        [SerializeField] private string _secondaryActionLabel = "CLOSE";

        public UnityResourceRagAuthMode AuthMode
        {
            get => _authMode;
            set => _authMode = value;
        }

        public UnityResourceRagDraftTemplateMode DraftTemplateMode
        {
            get => _draftTemplateMode;
            set => _draftTemplateMode = value;
        }

        public string SidecarRepoRoot
        {
            get => _sidecarRepoRoot;
            set => _sidecarRepoRoot = NormalizePath(value);
        }

        public string PythonExecutable
        {
            get => string.IsNullOrWhiteSpace(_pythonExecutable) ? GetDefaultPythonCommand() : _pythonExecutable;
            set => _pythonExecutable = string.IsNullOrWhiteSpace(value) ? GetDefaultPythonCommand() : value.Trim();
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
            get => string.IsNullOrWhiteSpace(_goal) ? GetSuggestedGoal(DraftTemplateMode) : _goal;
            set => _goal = string.IsNullOrWhiteSpace(value) ? GetSuggestedGoal(DraftTemplateMode) : value.Trim();
        }

        public string ScreenName
        {
            get => string.IsNullOrWhiteSpace(_screenName) ? GetSuggestedScreenName(DraftTemplateMode) : _screenName.Trim();
            set => _screenName = string.IsNullOrWhiteSpace(value) ? GetSuggestedScreenName(DraftTemplateMode) : value.Trim();
        }

        public string Title
        {
            get => string.IsNullOrWhiteSpace(_title) ? GetSuggestedTitle(DraftTemplateMode) : _title;
            set => _title = string.IsNullOrWhiteSpace(value) ? GetSuggestedTitle(DraftTemplateMode) : value.Trim();
        }

        public string Body
        {
            get => string.IsNullOrWhiteSpace(_body) ? GetSuggestedBody(DraftTemplateMode) : _body;
            set => _body = string.IsNullOrWhiteSpace(value) ? GetSuggestedBody(DraftTemplateMode) : value.Trim();
        }

        public string PrimaryActionLabel
        {
            get => string.IsNullOrWhiteSpace(_primaryActionLabel) ? GetSuggestedPrimaryAction(DraftTemplateMode) : _primaryActionLabel;
            set => _primaryActionLabel = string.IsNullOrWhiteSpace(value) ? GetSuggestedPrimaryAction(DraftTemplateMode) : value.Trim();
        }

        public string SecondaryActionLabel
        {
            get => string.IsNullOrWhiteSpace(_secondaryActionLabel) ? GetSuggestedSecondaryAction(DraftTemplateMode) : _secondaryActionLabel;
            set => _secondaryActionLabel = string.IsNullOrWhiteSpace(value) ? GetSuggestedSecondaryAction(DraftTemplateMode) : value.Trim();
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

        public string EffectiveTemplateMode
        {
            get
            {
                switch (DraftTemplateMode)
                {
                    case UnityResourceRagDraftTemplateMode.Hud:
                        return "hud";
                    case UnityResourceRagDraftTemplateMode.List:
                        return "list";
                    default:
                        return "popup";
                }
            }
        }

        public void EnsureDefaults()
        {
            if (string.IsNullOrWhiteSpace(SidecarRepoRoot) && TryDetectSidecarRuntimeRoot(out var detectedRepoRoot))
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

        public void ApplyDraftTemplateDefaults()
        {
            Goal = GetSuggestedGoal(DraftTemplateMode);
            ScreenName = GetSuggestedScreenName(DraftTemplateMode);
            Title = GetSuggestedTitle(DraftTemplateMode);
            Body = GetSuggestedBody(DraftTemplateMode);
            PrimaryActionLabel = GetSuggestedPrimaryAction(DraftTemplateMode);
            SecondaryActionLabel = GetSuggestedSecondaryAction(DraftTemplateMode);
        }

        public void SaveSettings()
        {
            Save(true);
        }

        public static string DefaultCodexConfigPath()
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".codex", "config.toml");
        }

        public static string GetDefaultPythonCommand()
        {
            return Application.platform == RuntimePlatform.WindowsEditor ? "py" : LegacyDefaultPythonExecutable;
        }

        public static string DefaultCodexAuthFilePath()
        {
            string codexHome = Environment.GetEnvironmentVariable("CODEX_HOME");
            string baseDirectory = string.IsNullOrWhiteSpace(codexHome)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".codex")
                : codexHome;
            return Path.GetFullPath(Path.Combine(baseDirectory, "auth.json"));
        }

        public static bool IsFullSidecarCheckoutRoot(string candidatePath)
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
                && File.Exists(Path.Combine(normalized, "pipeline", "mcp", "local_runner.py"))
                && File.Exists(Path.Combine(normalized, "Packages", "com.hanjo92.unity-resource-rag", "package.json"));
        }

        public static bool IsPackagedSidecarBundleRoot(string candidatePath)
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

            return File.Exists(Path.Combine(normalized, SidecarBundleManifestFileName))
                && File.Exists(Path.Combine(normalized, "requirements.txt"))
                && File.Exists(Path.Combine(normalized, "pipeline", "mcp", "server.py"))
                && File.Exists(Path.Combine(normalized, "pipeline", "mcp", "local_runner.py"));
        }

        public static bool IsSidecarRuntimeRoot(string candidatePath)
        {
            return IsFullSidecarCheckoutRoot(candidatePath) || IsPackagedSidecarBundleRoot(candidatePath);
        }

        public static bool IsSidecarRepoRoot(string candidatePath)
        {
            return IsSidecarRuntimeRoot(candidatePath);
        }

        public static string DescribeSidecarRuntimeRoot(string candidatePath)
        {
            if (IsPackagedSidecarBundleRoot(candidatePath))
            {
                return "portable sidecar bundle";
            }

            if (IsFullSidecarCheckoutRoot(candidatePath))
            {
                return "full unity-resource-rag checkout";
            }

            return "invalid sidecar runtime";
        }

        public static bool TryDetectSidecarRuntimeRoot(out string repoRoot)
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
                if (!IsSidecarRuntimeRoot(candidate))
                {
                    continue;
                }

                repoRoot = candidate;
                return true;
            }

            return false;
        }

        public static bool TryDetectSidecarRepoRoot(out string repoRoot)
        {
            return TryDetectSidecarRuntimeRoot(out repoRoot);
        }

        public static string GetSuggestedGoal(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "resource hud";
                case UnityResourceRagDraftTemplateMode.List:
                    return "inventory list";
                default:
                    return "reward popup";
            }
        }

        public static string GetSuggestedScreenName(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "ResourceHudDraft";
                case UnityResourceRagDraftTemplateMode.List:
                    return "InventoryListDraft";
                default:
                    return "ResourceRagDraft";
            }
        }

        public static string GetSuggestedTitle(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "Night Shift HUD";
                case UnityResourceRagDraftTemplateMode.List:
                    return "Night Shift Inventory";
                default:
                    return "Reward Unlocked";
            }
        }

        public static string GetSuggestedBody(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "Track health, currency, and active shift bonuses in a compact HUD draft.";
                case UnityResourceRagDraftTemplateMode.List:
                    return "Catalog-first list draft for inventory, shop, or mission rows.";
                default:
                    return "Catalog-first popup draft";
            }
        }

        public static string GetSuggestedPrimaryAction(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "BOOST";
                case UnityResourceRagDraftTemplateMode.List:
                    return "OPEN";
                default:
                    return "CLAIM";
            }
        }

        public static string GetSuggestedSecondaryAction(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "MAP";
                case UnityResourceRagDraftTemplateMode.List:
                    return "CLOSE";
                default:
                    return "CLOSE";
            }
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

        public static bool IsGenericPythonCommand(string command)
        {
            if (string.IsNullOrWhiteSpace(command))
            {
                return true;
            }

            string normalized = NormalizeCommandText(command);
            return string.Equals(normalized, NormalizeCommandText(GetDefaultPythonCommand()), StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalized, LegacyDefaultPythonExecutable, StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalized, "python", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalized, "py", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalized, "py -3", StringComparison.OrdinalIgnoreCase);
        }

        public static bool TrySplitCommand(string rawCommand, out string fileName, out List<string> arguments)
        {
            fileName = string.Empty;
            arguments = new List<string>();
            if (string.IsNullOrWhiteSpace(rawCommand))
            {
                return false;
            }

            MatchCollection matches = CommandTokenRegex.Matches(rawCommand.Trim());
            if (matches.Count == 0)
            {
                return false;
            }

            foreach (Match match in matches)
            {
                if (!match.Success)
                {
                    continue;
                }

                string token = match.Groups[1].Success ? match.Groups[1].Value : match.Groups[2].Value;
                if (string.IsNullOrWhiteSpace(token))
                {
                    continue;
                }

                if (string.IsNullOrWhiteSpace(fileName))
                {
                    fileName = ExpandCommandToken(token);
                }
                else
                {
                    arguments.Add(token);
                }
            }

            return !string.IsNullOrWhiteSpace(fileName);
        }

        public static string JoinCommandArguments(IEnumerable<string> arguments)
        {
            if (arguments == null)
            {
                return string.Empty;
            }

            var builder = new StringBuilder();
            foreach (string argument in arguments)
            {
                if (argument == null)
                {
                    continue;
                }

                if (builder.Length > 0)
                {
                    builder.Append(' ');
                }

                builder.Append(QuoteCommandArgument(argument));
            }

            return builder.ToString();
        }

        public static ProcessStartInfo CreateCommandStartInfo(string commandText, string workingDirectory, IEnumerable<string> arguments)
        {
            if (!TrySplitCommand(commandText, out string fileName, out List<string> prefixArguments))
            {
                throw new ArgumentException("The command is empty.", nameof(commandText));
            }

            if (arguments != null)
            {
                prefixArguments.AddRange(arguments);
            }

            return new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = JoinCommandArguments(prefixArguments),
                WorkingDirectory = workingDirectory,
            };
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
            return IsGenericPythonCommand(_pythonExecutable);
        }

        private static IEnumerable<string> EnumeratePythonCandidates(string sidecarRepoRoot)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var candidates = new List<string>
            {
                SafePathCombine(sidecarRepoRoot, ".venv", "Scripts", "python.exe"),
                SafePathCombine(sidecarRepoRoot, ".venv", "bin", "python"),
            };

            if (Application.platform == RuntimePlatform.WindowsEditor)
            {
                candidates.AddRange(new[]
                {
                    "py -3",
                    "py",
                    "python",
                    "python3",
                });
            }
            else
            {
                candidates.AddRange(new[]
                {
                    "/opt/homebrew/Caskroom/miniforge/base/bin/python3",
                    "/opt/homebrew/bin/python3",
                    "/opt/homebrew/bin/python",
                    "/usr/local/bin/python3",
                    "/usr/local/bin/python",
                    "python3",
                    "python",
                });
            }

            foreach (string candidate in candidates)
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
                ProcessStartInfo startInfo = CreateCommandStartInfo(
                    pythonExecutable,
                    string.IsNullOrWhiteSpace(sidecarRepoRoot) ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) : sidecarRepoRoot,
                    new[] { "-c", "import pydantic" });
                startInfo.RedirectStandardOutput = true;
                startInfo.RedirectStandardError = true;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;

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
                ProcessStartInfo startInfo = CreateCommandStartInfo(
                    pythonExecutable,
                    string.IsNullOrWhiteSpace(sidecarRepoRoot) ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) : sidecarRepoRoot,
                    new[] { "-c", "import sys; print(sys.executable)" });
                startInfo.RedirectStandardOutput = true;
                startInfo.RedirectStandardError = true;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;

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

        private static string NormalizeCommandText(string rawCommand)
        {
            return Regex.Replace(rawCommand.Trim(), "\\s+", " ");
        }

        private static string ExpandCommandToken(string token)
        {
            if (string.IsNullOrWhiteSpace(token))
            {
                return string.Empty;
            }

            string expanded = Environment.ExpandEnvironmentVariables(token.Trim());
            return expanded.Contains(Path.DirectorySeparatorChar.ToString()) || expanded.Contains(Path.AltDirectorySeparatorChar.ToString())
                ? NormalizePath(expanded)
                : expanded;
        }

        private static string QuoteCommandArgument(string argument)
        {
            if (string.IsNullOrEmpty(argument))
            {
                return "\"\"";
            }

            bool needsQuotes = false;
            for (int index = 0; index < argument.Length; index++)
            {
                char character = argument[index];
                if (char.IsWhiteSpace(character) || character == '"')
                {
                    needsQuotes = true;
                    break;
                }
            }

            if (!needsQuotes)
            {
                return argument;
            }

            var builder = new StringBuilder();
            builder.Append('"');

            int backslashCount = 0;
            foreach (char character in argument)
            {
                if (character == '\\')
                {
                    backslashCount++;
                    continue;
                }

                if (character == '"')
                {
                    builder.Append('\\', backslashCount * 2 + 1);
                    builder.Append('"');
                    backslashCount = 0;
                    continue;
                }

                if (backslashCount > 0)
                {
                    builder.Append('\\', backslashCount);
                    backslashCount = 0;
                }

                builder.Append(character);
            }

            if (backslashCount > 0)
            {
                builder.Append('\\', backslashCount * 2);
            }

            builder.Append('"');
            return builder.ToString();
        }
    }
}
