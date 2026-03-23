using System.IO;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagWindow : EditorWindow
    {
        private Vector2 _scrollPosition;
        private string _setupReport = string.Empty;
        private string _bootstrapReport = string.Empty;
        private string _readinessReport = string.Empty;
        private string _buildReport = string.Empty;
        private string _captureReport = string.Empty;
        private string _repairReport = string.Empty;
        private string _caseCaptureReport = string.Empty;
        private string _buildPhase = "Idle";
        private string _caseName = string.Empty;
        private string _caseNotes = string.Empty;
        private bool _showAdvancedSetup;
        private bool _isReadinessRunning;
        private bool _isBootstrapRunning;
        private bool _isBuildRunning;
        private bool _isCaptureRunning;
        private bool _isRepairRunning;
        private UnityResourceRagLocalToolResult _doctorResult;
        private UnityResourceRagLocalToolResult _buildResult;
        private UnityResourceRagLocalToolResult _captureResult;
        private UnityResourceRagLocalToolResult _repairResult;

        [MenuItem("Window/Unity Resource RAG")]
        public static void Open()
        {
            UnityResourceRagWindow window = GetWindow<UnityResourceRagWindow>("Unity Resource RAG");
            window.minSize = new Vector2(560f, 760f);
            window.Show();
        }

        private void OnEnable()
        {
            UnityResourceRagEditorSettings settings = UnityResourceRagEditorSettings.instance;
            settings.EnsureDefaults();
            if (string.IsNullOrWhiteSpace(_caseName))
            {
                _caseName = settings.ScreenName;
            }

            if (string.IsNullOrWhiteSpace(_readinessReport))
            {
                _readinessReport = UnityResourceRagReportFormatter.FormatReadinessRefreshReport(settings, null);
            }
        }

        private void OnGUI()
        {
            UnityResourceRagEditorSettings settings = UnityResourceRagEditorSettings.instance;
            settings.EnsureDefaults();

            if (string.IsNullOrWhiteSpace(_caseName))
            {
                _caseName = GetSuggestedCaseName(settings);
            }

            using var scrollScope = new EditorGUILayout.ScrollViewScope(_scrollPosition);
            _scrollPosition = scrollScope.scrollPosition;

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Unity Resource RAG", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "This window is the Unity Resource RAG add-on layered on top of Unity MCP. Use Quick Setup to configure the connection, check Readiness, run Start UI Build, and continue with Capture & Repair and Case Export from the same window.",
                MessageType.Info);

            bool settingsChanged = false;

            EditorGUI.BeginChangeCheck();
            DrawReadinessSection(settings);
            DrawQuickSetupSection(settings);
            DrawBuildSection(settings);
            DrawFollowUpSection(settings);
            DrawCaseCaptureSection(settings);
            settingsChanged = EditorGUI.EndChangeCheck();

            if (settingsChanged)
            {
                settings.SaveSettings();
            }
        }

        private void DrawReadinessSection(UnityResourceRagEditorSettings settings)
        {
            EditorGUILayout.Space(6f);
            EditorGUILayout.LabelField("Readiness Dashboard", EditorStyles.boldLabel);

            foreach (UnityResourceRagReadinessItem item in UnityResourceRagReportFormatter.BuildReadinessItems(settings, _doctorResult))
            {
                DrawReadinessItem(item);
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(_isReadinessRunning || _isBuildRunning || _isCaptureRunning || _isRepairRunning))
                {
                    if (GUILayout.Button(_isReadinessRunning ? "Refreshing Readiness..." : "Refresh Readiness", GUILayout.Height(26f)))
                    {
                        RunReadinessRefresh(settings);
                    }
                }

                using (new EditorGUI.DisabledScope(_isBootstrapRunning || _isBuildRunning || _isCaptureRunning || _isRepairRunning))
                {
                    if (GUILayout.Button(_isBootstrapRunning ? "Bootstrapping Python..." : "Bootstrap Python Runtime", GUILayout.Height(26f)))
                    {
                        RunRuntimeBootstrap(settings);
                    }
                }
            }

            if (!string.IsNullOrWhiteSpace(_bootstrapReport))
            {
                EditorGUILayout.HelpBox(_bootstrapReport, MessageType.None);
            }

            if (!string.IsNullOrWhiteSpace(_readinessReport))
            {
                EditorGUILayout.HelpBox(_readinessReport, MessageType.None);
            }
        }

        private void DrawQuickSetupSection(UnityResourceRagEditorSettings settings)
        {
            UnityResourceRagAuthProfileInfo authProfile = UnityResourceRagAuthProfilePresenter.Describe(settings);

            EditorGUILayout.Space(10f);
            EditorGUILayout.LabelField("Quick Setup", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Quick Setup configures the Unity MCP transport, custom tool exposure, and the Codex sidecar entry. Python dependencies are handled by Bootstrap Python Runtime below.",
                MessageType.None);

            settings.AuthMode = (UnityResourceRagAuthMode)EditorGUILayout.EnumPopup("Sign-in Method", settings.AuthMode);
            authProfile = UnityResourceRagAuthProfilePresenter.Describe(settings);

            using (new EditorGUILayout.VerticalScope("box"))
            {
                EditorGUILayout.LabelField(authProfile.Title, EditorStyles.boldLabel);
                EditorGUILayout.HelpBox(authProfile.Summary, MessageType.None);
                EditorGUILayout.LabelField("What to expect", EditorStyles.miniBoldLabel);
                EditorGUILayout.LabelField(authProfile.NextStep, EditorStyles.wordWrappedMiniLabel);
            }

            DrawPathField(
                "Sidecar Repo Root",
                settings.SidecarRepoRoot,
                "Browse",
                () => settings.SidecarRepoRoot = EditorUtility.OpenFolderPanel("Select unity-resource-rag repo root", settings.SidecarRepoRoot, string.Empty));

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Auto Detect Repo Root", GUILayout.Width(180f)))
                {
                    if (UnityResourceRagEditorSettings.TryDetectSidecarRepoRoot(out string detectedRepoRoot))
                    {
                        settings.SidecarRepoRoot = detectedRepoRoot;
                    }
                    else
                    {
                        _setupReport = "Auto detection could not find a full unity-resource-rag checkout. Set Sidecar Repo Root manually.";
                    }
                }

                GUILayout.FlexibleSpace();
            }

            if (authProfile.ShowApiKeyEnvField)
            {
                settings.ProviderApiKeyEnv = EditorGUILayout.TextField("Environment Variable Name", settings.ProviderApiKeyEnv);
            }

            _showAdvancedSetup = EditorGUILayout.Foldout(_showAdvancedSetup, "Advanced Paths & Overrides", true);
            if (_showAdvancedSetup)
            {
                settings.PythonExecutable = EditorGUILayout.TextField("Python Executable", settings.PythonExecutable);
                settings.UnityMcpBaseUrl = EditorGUILayout.TextField("Unity MCP Base URL", settings.UnityMcpBaseUrl);
                settings.CodexConfigPath = EditorGUILayout.TextField("Codex Config Path", settings.CodexConfigPath);

                if (authProfile.ShowCodexAuthOverrideField)
                {
                    settings.CodexAuthFile = EditorGUILayout.TextField("Custom Codex Auth File (Optional)", settings.CodexAuthFile);
                }
                else if (authProfile.ShowApiKeyEnvField)
                {
                    EditorGUILayout.HelpBox(
                        "Only enter the environment variable name here. Do not paste the API key value into Unity.",
                        MessageType.None);
                }
            }

            if (GUILayout.Button("Quick Setup", GUILayout.Height(28f)))
            {
                RunQuickSetup(settings);
            }

            if (!string.IsNullOrWhiteSpace(_setupReport))
            {
                EditorGUILayout.HelpBox(_setupReport, MessageType.None);
            }
        }

        private void DrawBuildSection(UnityResourceRagEditorSettings settings)
        {
            EditorGUILayout.Space(10f);
            EditorGUILayout.LabelField("Start UI Build", EditorStyles.boldLabel);
            DrawPathField(
                "Reference Image",
                settings.ReferenceImagePath,
                "Browse",
                () => settings.ReferenceImagePath = EditorUtility.OpenFilePanel("Select reference image", settings.ReferenceImagePath, "png,jpg,jpeg"));

            EditorGUILayout.HelpBox(
                "If a reference image is provided, the window runs the reference-first build path. If it is empty, it falls back to the catalog-first draft path. The window rechecks readiness before the build and continues to Unity apply on success.",
                MessageType.None);

            bool hasReferenceImage = !string.IsNullOrWhiteSpace(settings.ReferenceImagePath);
            if (!hasReferenceImage)
            {
                settings.DraftTemplateMode = (UnityResourceRagDraftTemplateMode)EditorGUILayout.EnumPopup("Draft Template", settings.DraftTemplateMode);
                EditorGUILayout.HelpBox(GetDraftTemplateHelpText(settings.DraftTemplateMode), MessageType.None);

                using (new EditorGUILayout.HorizontalScope())
                {
                    if (GUILayout.Button("Use Suggested Copy", GUILayout.Width(180f)))
                    {
                        settings.ApplyDraftTemplateDefaults();
                    }

                    GUILayout.FlexibleSpace();
                }
            }

            settings.Goal = EditorGUILayout.TextField("Goal", settings.Goal);
            settings.ScreenName = EditorGUILayout.TextField("Screen Name", settings.ScreenName);
            settings.Title = EditorGUILayout.TextField("Title", settings.Title);
            settings.Body = EditorGUILayout.TextField("Body", settings.Body);
            settings.PrimaryActionLabel = EditorGUILayout.TextField("Primary Action", settings.PrimaryActionLabel);
            settings.SecondaryActionLabel = EditorGUILayout.TextField("Secondary Action", settings.SecondaryActionLabel);
            settings.UnityMcpTimeoutMs = EditorGUILayout.IntField("Unity MCP Timeout (ms)", settings.UnityMcpTimeoutMs);
            settings.ApplyInUnity = EditorGUILayout.Toggle("Apply In Unity", settings.ApplyInUnity);
            settings.ValidateBeforeApply = EditorGUILayout.Toggle("Validate Before Apply", settings.ValidateBeforeApply);
            settings.ForceReindex = EditorGUILayout.Toggle("Force Reindex", settings.ForceReindex);

            if (_isBuildRunning)
            {
                EditorGUILayout.HelpBox(_buildPhase, MessageType.Info);
            }

            using (new EditorGUI.DisabledScope(_isBuildRunning || _isReadinessRunning || _isCaptureRunning || _isRepairRunning))
            {
                if (GUILayout.Button(_isBuildRunning ? "Start UI Build (Running...)" : "Start UI Build", GUILayout.Height(28f)))
                {
                    RunStartUiBuild(settings);
                }
            }

            DrawBuildArtifacts();

            if (!string.IsNullOrWhiteSpace(_buildReport))
            {
                EditorGUILayout.HelpBox(_buildReport, MessageType.None);
            }
        }

        private void DrawFollowUpSection(UnityResourceRagEditorSettings settings)
        {
            EditorGUILayout.Space(10f);
            EditorGUILayout.LabelField("Capture & Repair", EditorStyles.boldLabel);

            bool canCapture = CanCaptureCurrentResult();
            bool canRepair = CanRepairCurrentResult(settings);
            if (!canCapture)
            {
                EditorGUILayout.HelpBox("A successful build result is required before you can capture the current Unity output.", MessageType.None);
            }
            else if (!canRepair)
            {
                EditorGUILayout.HelpBox(
                    string.IsNullOrWhiteSpace(settings.ReferenceImagePath)
                        ? "Without a reference image, this flow stops at result capture. Repair handoff is only available when a reference image is present."
                        : "After capture, you can run Repair Handoff to generate a mismatch report against the reference.",
                    MessageType.None);
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(!canCapture || _isBuildRunning || _isReadinessRunning || _isCaptureRunning || _isRepairRunning))
                {
                    if (GUILayout.Button(_isCaptureRunning ? "Capturing Result..." : "Capture Result", GUILayout.Height(26f)))
                    {
                        RunCaptureResult(settings);
                    }
                }

                using (new EditorGUI.DisabledScope(!canRepair || _isBuildRunning || _isReadinessRunning || _isCaptureRunning || _isRepairRunning))
                {
                    if (GUILayout.Button(_isRepairRunning ? "Running Repair..." : "Run Repair Handoff", GUILayout.Height(26f)))
                    {
                        RunRepairHandoff(settings);
                    }
                }
            }

            if (!string.IsNullOrWhiteSpace(_captureReport))
            {
                EditorGUILayout.HelpBox(_captureReport, MessageType.None);
            }

            if (!string.IsNullOrWhiteSpace(_repairReport))
            {
                EditorGUILayout.HelpBox(_repairReport, MessageType.None);
            }
        }

        private void DrawCaseCaptureSection(UnityResourceRagEditorSettings settings)
        {
            EditorGUILayout.Space(10f);
            EditorGUILayout.LabelField("Case Export", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Save build, capture, and repair results as markdown and JSON case reports so real-project quality reviews are easy to track and attach to follow-up issues or release notes.",
                MessageType.None);

            _caseName = EditorGUILayout.TextField("Case Name", _caseName);
            EditorGUILayout.LabelField("Notes");
            _caseNotes = EditorGUILayout.TextArea(_caseNotes, GUILayout.MinHeight(84f));

            using (new EditorGUI.DisabledScope(_buildResult == null || !_buildResult.Success || _isBuildRunning || _isCaptureRunning || _isRepairRunning))
            {
                if (GUILayout.Button("Export Case Report", GUILayout.Height(26f)))
                {
                    ExportCaseCapture(settings);
                }
            }

            if (!string.IsNullOrWhiteSpace(_caseCaptureReport))
            {
                EditorGUILayout.HelpBox(_caseCaptureReport, MessageType.None);
            }
        }

        private void DrawReadinessItem(UnityResourceRagReadinessItem item)
        {
            using var box = new EditorGUILayout.VerticalScope("box");
            EditorGUILayout.LabelField($"{UnityResourceRagReportFormatter.DescribeReadinessLevel(item.Level)} - {item.Title}", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(item.Summary, ToMessageType(item.Level));
            if (!string.IsNullOrWhiteSpace(item.NextStep))
            {
                EditorGUILayout.LabelField("Next", EditorStyles.miniBoldLabel);
                EditorGUILayout.LabelField(item.NextStep, EditorStyles.wordWrappedMiniLabel);
            }
        }

        private void DrawBuildArtifacts()
        {
            if (_buildResult == null || !_buildResult.Success || _buildResult.Payload == null)
            {
                return;
            }

            JObject payload = _buildResult.Payload;
            using var box = new EditorGUILayout.VerticalScope("box");
            EditorGUILayout.LabelField("Last Build Output", EditorStyles.boldLabel);
            EditorGUILayout.LabelField("Flow", UnityResourceRagReportFormatter.ExtractRouteLabel(payload));
            DrawSelectableArtifact("Blueprint", UnityResourceRagReportFormatter.ExtractBlueprintPath(payload));
            DrawSelectableArtifact("Handoff", UnityResourceRagReportFormatter.ExtractHandoffPath(payload));
            DrawSelectableArtifact("Applied Root", UnityResourceRagReportFormatter.ExtractAppliedRootName(payload));
            DrawSelectableArtifact("Verify Target", UnityResourceRagReportFormatter.ExtractVerifyTarget(payload));
        }

        private void DrawSelectableArtifact(string label, string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return;
            }

            EditorGUILayout.LabelField(label, EditorStyles.miniBoldLabel);
            EditorGUILayout.LabelField(value, EditorStyles.wordWrappedMiniLabel);
        }

        private void RunQuickSetup(UnityResourceRagEditorSettings settings)
        {
            EditorUtility.DisplayProgressBar("Unity Resource RAG", "Running Quick Setup...", 0.25f);
            try
            {
                UnityResourceRagQuickSetupResult result = UnityResourceRagQuickSetupService.Run(settings);
                _setupReport = UnityResourceRagReportFormatter.FormatQuickSetupReport(result);
                if (result.Success)
                {
                    Debug.Log("[Unity Resource RAG] " + result.Summary);
                }
                else
                {
                    Debug.LogWarning("[Unity Resource RAG] " + result.Summary);
                }
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }

            RunReadinessRefresh(settings);
        }

        private void RunRuntimeBootstrap(UnityResourceRagEditorSettings settings)
        {
            _isBootstrapRunning = true;
            _bootstrapReport = "Starting Python runtime bootstrap.\nThe window is preparing a repo-local `.venv` and installing requirements in the background.";
            Repaint();

            if (!UnityResourceRagRuntimeBootstrapService.TryRunAsync(settings, OnRuntimeBootstrapCompleted, out string error))
            {
                _isBootstrapRunning = false;
                _bootstrapReport = string.IsNullOrWhiteSpace(error) ? "Python runtime bootstrap failed to start." : error;
                Debug.LogError("[Unity Resource RAG] " + _bootstrapReport);
                Repaint();
            }
        }

        private void OnRuntimeBootstrapCompleted(UnityResourceRagRuntimeBootstrapResult result)
        {
            _isBootstrapRunning = false;
            _bootstrapReport = UnityResourceRagReportFormatter.FormatRuntimeBootstrapReport(result);

            if (result.Success)
            {
                Debug.Log("[Unity Resource RAG] " + result.Summary);
                RunReadinessRefresh(UnityResourceRagEditorSettings.instance);
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Summary);
                Repaint();
            }
        }

        private void RunReadinessRefresh(UnityResourceRagEditorSettings settings)
        {
            _isReadinessRunning = true;
            _readinessReport = "Refreshing readiness status.";
            Repaint();

            if (!UnityResourceRagLocalRunner.TryRunDoctorAsync(settings, OnReadinessRefreshCompleted, out string error))
            {
                _isReadinessRunning = false;
                _doctorResult = null;
                _readinessReport = UnityResourceRagReportFormatter.FormatReadinessRefreshReport(settings, new UnityResourceRagLocalToolResult
                {
                    Success = false,
                    Error = string.IsNullOrWhiteSpace(error) ? "Readiness refresh failed to start." : error,
                });
                Debug.LogError("[Unity Resource RAG] " + _readinessReport);
                Repaint();
            }
        }

        private void OnReadinessRefreshCompleted(UnityResourceRagLocalToolResult result)
        {
            _isReadinessRunning = false;
            _doctorResult = result;
            _readinessReport = UnityResourceRagReportFormatter.FormatReadinessRefreshReport(UnityResourceRagEditorSettings.instance, result);

            if (result.Success)
            {
                Debug.Log("[Unity Resource RAG] Readiness refresh completed.");
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Error);
            }

            Repaint();
        }

        private void RunStartUiBuild(UnityResourceRagEditorSettings settings)
        {
            if (_isBuildRunning)
            {
                return;
            }

            _isBuildRunning = true;
            _buildPhase = "1/2 Checking readiness before build...";
            _buildReport = "Rechecking readiness before the build starts.";
            _captureResult = null;
            _repairResult = null;
            _captureReport = string.Empty;
            _repairReport = string.Empty;
            Repaint();

            if (!UnityResourceRagLocalRunner.TryRunDoctorAsync(settings, OnBuildReadinessCompleted, out string error))
            {
                _isBuildRunning = false;
                _buildPhase = "Build blocked";
                _buildReport = string.IsNullOrWhiteSpace(error) ? "Start UI Build failed to start." : error;
                Debug.LogError("[Unity Resource RAG] " + _buildReport);
                Repaint();
            }
        }

        private void OnBuildReadinessCompleted(UnityResourceRagLocalToolResult result)
        {
            UnityResourceRagEditorSettings settings = UnityResourceRagEditorSettings.instance;
            _doctorResult = result;
            _readinessReport = UnityResourceRagReportFormatter.FormatReadinessRefreshReport(settings, result);

            if (!result.Success)
            {
                _isBuildRunning = false;
                _buildPhase = "Build blocked";
                _buildReport = "The build did not start because the readiness check itself could not be completed.\n" + _readinessReport;
                Debug.LogError("[Unity Resource RAG] " + result.Error);
                Repaint();
                return;
            }

            string overallStatus = result.Payload?.Value<string>("overallStatus") ?? string.Empty;
            if (string.Equals(overallStatus, "error", System.StringComparison.OrdinalIgnoreCase))
            {
                _isBuildRunning = false;
                _buildPhase = "Build blocked";
                _buildReport = "The build did not start because one or more blocking readiness items still need attention.\n" + _readinessReport;
                Debug.LogWarning("[Unity Resource RAG] Build was blocked by readiness.");
                Repaint();
                return;
            }

            string routeLabel = string.IsNullOrWhiteSpace(settings.ReferenceImagePath)
                ? $"{settings.DraftTemplateMode} catalog-first draft"
                : "reference-first build";
            _buildPhase = $"2/2 Running {routeLabel} and Unity apply...";
            _buildReport = "Running blueprint generation and Unity apply.";
            Repaint();

            if (!UnityResourceRagLocalRunner.TryRunToolAsync(
                    settings,
                    "start_ui_build",
                    UnityResourceRagLocalRunner.BuildStartUiBuildPayload(settings, false, false),
                    OnStartUiBuildCompleted,
                    out string error))
            {
                _isBuildRunning = false;
                _buildPhase = "Build failed";
                _buildReport = string.IsNullOrWhiteSpace(error) ? "Build failed to start." : error;
                Debug.LogError("[Unity Resource RAG] " + _buildReport);
                Repaint();
            }
        }

        private void OnStartUiBuildCompleted(UnityResourceRagLocalToolResult result)
        {
            _isBuildRunning = false;
            _buildResult = result;
            _buildPhase = result.Success ? "Build completed" : "Build failed";
            _buildReport = UnityResourceRagReportFormatter.FormatBuildReport(result);

            if (result.Success)
            {
                if (string.IsNullOrWhiteSpace(_caseName) || _caseName == UnityResourceRagEditorSettings.instance.ScreenName)
                {
                    _caseName = GetSuggestedCaseName(UnityResourceRagEditorSettings.instance);
                }

                Debug.Log("[Unity Resource RAG] " + result.Summary);
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Error);
            }

            Repaint();
        }

        private void RunCaptureResult(UnityResourceRagEditorSettings settings)
        {
            if (!CanCaptureCurrentResult())
            {
                return;
            }

            _isCaptureRunning = true;
            _captureReport = "Capturing the current Unity result.";
            Repaint();

            if (!UnityResourceRagLocalRunner.TryRunCaptureResultAsync(settings, _buildResult.Payload, OnCaptureCompleted, out string error))
            {
                _isCaptureRunning = false;
                _captureReport = string.IsNullOrWhiteSpace(error) ? "Capture Result failed to start." : error;
                Debug.LogError("[Unity Resource RAG] " + _captureReport);
                Repaint();
            }
        }

        private void OnCaptureCompleted(UnityResourceRagLocalToolResult result)
        {
            _isCaptureRunning = false;
            _captureResult = result;
            _captureReport = UnityResourceRagReportFormatter.FormatCaptureReport(result);
            if (result.Success)
            {
                Debug.Log("[Unity Resource RAG] " + result.Summary);
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Error);
            }

            Repaint();
        }

        private void RunRepairHandoff(UnityResourceRagEditorSettings settings)
        {
            if (!CanRepairCurrentResult(settings))
            {
                return;
            }

            string capturedImagePath = _captureResult.Payload?.Value<string>("capturedPath");
            string resolvedBlueprintPath = UnityResourceRagReportFormatter.ExtractBlueprintPath(_buildResult.Payload);
            string outputDirectory = BuildRepairOutputDirectory(capturedImagePath);

            _isRepairRunning = true;
            _repairReport = "Building a repair handoff from the captured result.";
            Repaint();

            if (!UnityResourceRagLocalRunner.TryRunVerificationRepairAsync(settings, capturedImagePath, resolvedBlueprintPath, outputDirectory, OnRepairCompleted, out string error))
            {
                _isRepairRunning = false;
                _repairReport = string.IsNullOrWhiteSpace(error) ? "Repair handoff failed to start." : error;
                Debug.LogError("[Unity Resource RAG] " + _repairReport);
                Repaint();
            }
        }

        private void OnRepairCompleted(UnityResourceRagLocalToolResult result)
        {
            _isRepairRunning = false;
            _repairResult = result;
            _repairReport = UnityResourceRagReportFormatter.FormatRepairReport(result);
            if (result.Success)
            {
                Debug.Log("[Unity Resource RAG] " + result.Summary);
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Error);
            }

            Repaint();
        }

        private void ExportCaseCapture(UnityResourceRagEditorSettings settings)
        {
            UnityResourceRagCaseCaptureResult result = UnityResourceRagCaseCaptureService.Export(
                settings,
                _buildResult,
                _captureResult,
                _repairResult,
                _caseName,
                _caseNotes);
            _caseCaptureReport = UnityResourceRagReportFormatter.FormatCaseCaptureReport(result);
            if (result.Success)
            {
                Debug.Log("[Unity Resource RAG] " + result.Summary);
            }
            else
            {
                Debug.LogError("[Unity Resource RAG] " + result.Summary);
            }
        }

        private bool CanCaptureCurrentResult()
        {
            if (_buildResult == null || !_buildResult.Success || _buildResult.Payload == null)
            {
                return false;
            }

            return UnityResourceRagReportFormatter.ExtractVerificationRequest(_buildResult.Payload) != null
                || !string.IsNullOrWhiteSpace(UnityResourceRagReportFormatter.ExtractVerifyTarget(_buildResult.Payload));
        }

        private bool CanRepairCurrentResult(UnityResourceRagEditorSettings settings)
        {
            if (_captureResult == null || !_captureResult.Success || _captureResult.Payload == null)
            {
                return false;
            }

            string capturedPath = _captureResult.Payload.Value<string>("capturedPath");
            if (string.IsNullOrWhiteSpace(capturedPath) || !File.Exists(capturedPath))
            {
                return false;
            }

            return !string.IsNullOrWhiteSpace(settings.ReferenceImagePath) && File.Exists(settings.ReferenceImagePath);
        }

        private string BuildRepairOutputDirectory(string capturedImagePath)
        {
            if (string.IsNullOrWhiteSpace(capturedImagePath))
            {
                return string.Empty;
            }

            try
            {
                string directory = Path.GetDirectoryName(capturedImagePath);
                string filename = Path.GetFileNameWithoutExtension(capturedImagePath);
                if (string.IsNullOrWhiteSpace(directory) || string.IsNullOrWhiteSpace(filename))
                {
                    return string.Empty;
                }

                return Path.Combine(directory, filename + ".repair-loop");
            }
            catch
            {
                return string.Empty;
            }
        }

        private string GetSuggestedCaseName(UnityResourceRagEditorSettings settings)
        {
            if (_buildResult != null && _buildResult.Success && _buildResult.Payload != null)
            {
                string fromBuild = UnityResourceRagReportFormatter.ExtractAppliedRootName(_buildResult.Payload);
                if (!string.IsNullOrWhiteSpace(fromBuild))
                {
                    return fromBuild;
                }
            }

            if (!string.IsNullOrWhiteSpace(settings.ScreenName))
            {
                return settings.ScreenName;
            }

            return "ResourceRagCase";
        }

        private static string GetDraftTemplateHelpText(UnityResourceRagDraftTemplateMode mode)
        {
            switch (mode)
            {
                case UnityResourceRagDraftTemplateMode.Hud:
                    return "HUD / Top Bar is best for resource bars, status overlays, and compact always-on screen chrome. The generated draft prioritizes a wide top-aligned shell with status text and icon slots.";
                case UnityResourceRagDraftTemplateMode.List:
                    return "List / Inventory is best for shop rows, inventory panels, and mission cards. The generated draft creates a reusable panel shell with three example rows so you can reshape it into your real list quickly.";
                default:
                    return "Popup / Modal is best for reward popups, confirm dialogs, and focused modal windows. The generated draft prioritizes a centered panel with title, body, highlight icon, and action labels.";
            }
        }

        private static void DrawPathField(string label, string value, string buttonLabel, System.Action onBrowse)
        {
            using var horizontal = new EditorGUILayout.HorizontalScope();
            EditorGUILayout.PrefixLabel(label);
            EditorGUILayout.SelectableLabel(string.IsNullOrWhiteSpace(value) ? "(not set)" : value, EditorStyles.textField, GUILayout.Height(EditorGUIUtility.singleLineHeight));
            if (GUILayout.Button(buttonLabel, GUILayout.Width(80f)))
            {
                onBrowse?.Invoke();
            }
        }

        private static MessageType ToMessageType(UnityResourceRagReadinessLevel level)
        {
            switch (level)
            {
                case UnityResourceRagReadinessLevel.Ready:
                    return MessageType.Info;
                case UnityResourceRagReadinessLevel.Attention:
                    return MessageType.Warning;
                default:
                    return MessageType.Error;
            }
        }
    }
}
