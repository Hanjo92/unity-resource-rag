using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagQuickSetupResult
    {
        public bool Success => Errors.Count == 0;
        public List<string> Steps { get; } = new List<string>();
        public List<string> Warnings { get; } = new List<string>();
        public List<string> Errors { get; } = new List<string>();
        public string Summary { get; set; } = string.Empty;
    }

    public static class UnityResourceRagQuickSetupService
    {
        private const string ProjectScopedToolsLocalHttpKey = "MCPForUnity.ProjectScopedTools.LocalHttp";
        private const string CustomToolRegistrationEnabledKey = "MCPForUnity.CustomToolRegistrationEnabled";
        private const string AutoRegisterEnabledKey = "MCPForUnity.AutoRegisterEnabled";
        private const int BridgeWarmupMaxAttempts = 8;
        private const int BridgeWarmupRetryDelayMs = 1000;
        private static readonly string[] ExpectedTools = { "index_project_resources", "query_ui_asset_catalog", "apply_ui_blueprint" };
        private static readonly string[] ExpectedResources = { "ui_asset_catalog" };
        private static bool _bridgeWarmupScheduled;

        public static UnityResourceRagQuickSetupResult Run(UnityResourceRagEditorSettings settings)
        {
            settings.EnsureDefaults();
            var result = new UnityResourceRagQuickSetupResult();

            ConfigureUnityMcpEditorPrefs(settings, result);
            EnableCustomTools(result);
            EnableCustomResources(result);
            RestartServerAndBridge(result);
            CheckAuthMode(settings, result);
            SyncCodexConfig(settings, result);

            settings.SaveSettings();
            result.Summary = BuildSummary(result);
            return result;
        }

        private static void ConfigureUnityMcpEditorPrefs(UnityResourceRagEditorSettings settings, UnityResourceRagQuickSetupResult result)
        {
            EditorConfigurationCache.Instance.SetUseHttpTransport(true);
            EditorConfigurationCache.Instance.SetHttpTransportScope("local");
            HttpEndpointUtility.SaveLocalBaseUrl(settings.UnityMcpBaseUrl);

            EditorPrefs.SetBool(ProjectScopedToolsLocalHttpKey, false);
            EditorPrefs.SetBool(CustomToolRegistrationEnabledKey, true);
            EditorPrefs.SetBool(AutoRegisterEnabledKey, true);
            EditorConfigurationCache.Instance.Refresh();

            result.Steps.Add($"Configured Unity MCP to use HTTP Local (`{settings.UnityMcpBaseUrl}`).");
            result.Steps.Add("Disabled Project Scoped Tools so custom tools are exposed directly.");
        }

        private static void EnableCustomTools(UnityResourceRagQuickSetupResult result)
        {
            IToolDiscoveryService discovery = MCPServiceLocator.ToolDiscovery;
            discovery.InvalidateCache();
            var discovered = discovery.DiscoverAllTools();

            foreach (string toolName in ExpectedTools)
            {
                bool found = false;
                foreach (ToolMetadata metadata in discovered)
                {
                    if (!string.Equals(metadata.Name, toolName, StringComparison.Ordinal))
                    {
                        continue;
                    }

                    found = true;
                    discovery.SetToolEnabled(toolName, true);
                    result.Steps.Add($"Enabled custom tool `{toolName}`.");
                    break;
                }

                if (!found)
                {
                    result.Warnings.Add($"Custom tool `{toolName}` has not been discovered yet. Reopen the window after Unity compilation finishes.");
                }
            }
        }

        private static void EnableCustomResources(UnityResourceRagQuickSetupResult result)
        {
            IResourceDiscoveryService discovery = MCPServiceLocator.ResourceDiscovery;
            discovery.InvalidateCache();
            var discovered = discovery.DiscoverAllResources();

            foreach (string resourceName in ExpectedResources)
            {
                bool found = false;
                foreach (ResourceMetadata metadata in discovered)
                {
                    if (!string.Equals(metadata.Name, resourceName, StringComparison.Ordinal))
                    {
                        continue;
                    }

                    found = true;
                    discovery.SetResourceEnabled(resourceName, true);
                    result.Steps.Add($"Enabled resource `{resourceName}`.");
                    break;
                }

                if (!found)
                {
                    result.Warnings.Add($"Resource `{resourceName}` has not been discovered yet. Confirm that Unity compilation has completed.");
                }
            }
        }

        private static void RestartServerAndBridge(UnityResourceRagQuickSetupResult result)
        {
            IServerManagementService server = MCPServiceLocator.Server;
            if (!server.CanStartLocalServer())
            {
                result.Errors.Add("Unity MCP Local HTTP Server cannot be started. Check the HTTP Local configuration again.");
                return;
            }

            server.StopManagedLocalHttpServer();
            bool started = server.StartLocalHttpServer();
            if (!started && !server.IsLocalHttpServerReachable())
            {
                result.Errors.Add("Failed to start the Unity MCP Local HTTP Server.");
                return;
            }

            WaitFor(server.IsLocalHttpServerReachable, 3000);
            result.Steps.Add("Restarted the Unity MCP Local HTTP Server.");
            ScheduleBridgeWarmup();
            result.Steps.Add("Scheduled MCP bridge startup in the background.");
            result.Warnings.Add("Bridge warmup continues asynchronously. Right after Quick Setup, also check the Unity Console or the Unity MCP window status.");
        }

        private static void CheckAuthMode(UnityResourceRagEditorSettings settings, UnityResourceRagQuickSetupResult result)
        {
            result.Steps.Add($"Python command: {settings.PythonExecutable}");

            if (settings.AuthMode == UnityResourceRagAuthMode.UseExistingCodexLogin)
            {
                if (settings.HasReadableCodexAuthFile)
                {
                    result.Steps.Add("Configured the window to reuse the current Codex sign-in.");
                }
                else
                {
                    result.Warnings.Add("No Codex sign-in was found in the default auth file locations. Hosted model calls may fail until you sign in again or point the window to a custom auth file override.");
                }
                return;
            }

            if (settings.AuthMode == UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable)
            {
                string envName = settings.ProviderApiKeyEnv;
                if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(envName)))
                {
                    result.Warnings.Add($"No value was found in the API key environment variable `{envName}`.");
                }
                else
                {
                    result.Steps.Add($"Configured the window to use the API key environment variable `{envName}`.");
                }
                return;
            }

            result.Steps.Add("Configured the window to stay in Offline local fallback mode.");
        }

        private static void SyncCodexConfig(UnityResourceRagEditorSettings settings, UnityResourceRagQuickSetupResult result)
        {
            UnityResourceRagCodexConfigResult syncResult = UnityResourceRagCodexConfigSync.EnsureSidecarServer(settings);
            if (syncResult.Success)
            {
                result.Steps.Add(syncResult.Summary);
            }
            else if (syncResult.Skipped)
            {
                result.Warnings.Add(syncResult.Summary);
            }
            else
            {
                result.Warnings.Add(syncResult.Summary);
            }
        }

        private static void WaitFor(Func<bool> predicate, int timeoutMs)
        {
            int elapsed = 0;
            while (elapsed < timeoutMs)
            {
                if (predicate())
                {
                    return;
                }

                Thread.Sleep(150);
                elapsed += 150;
            }
        }

        private static void ScheduleBridgeWarmup()
        {
            if (_bridgeWarmupScheduled)
            {
                return;
            }

            _bridgeWarmupScheduled = true;
            EditorApplication.delayCall += StartBridgeWarmupAsync;
        }

        private static async void StartBridgeWarmupAsync()
        {
            string lastMessage = "브리지 시작 전입니다.";
            try
            {
                for (int attempt = 1; attempt <= BridgeWarmupMaxAttempts; attempt++)
                {
                    bool started = await MCPServiceLocator.Bridge.StartAsync();
                    if (!started)
                    {
                        lastMessage = $"브리지 시작 실패 (시도 {attempt}/{BridgeWarmupMaxAttempts}).";
                    }
                    else
                    {
                        BridgeVerificationResult verification = await MCPServiceLocator.Bridge.VerifyAsync();
                        if (verification.Success)
                        {
                            Debug.Log($"[Unity Resource RAG] MCP bridge warmup completed successfully on attempt {attempt}.");
                            return;
                        }

                        lastMessage = string.IsNullOrWhiteSpace(verification.Message)
                            ? $"브리지 검증 미완료 (시도 {attempt}/{BridgeWarmupMaxAttempts})."
                            : $"브리지 검증 미완료 (시도 {attempt}/{BridgeWarmupMaxAttempts}): {verification.Message}";
                    }

                    if (attempt < BridgeWarmupMaxAttempts)
                    {
                        await Task.Delay(BridgeWarmupRetryDelayMs);
                    }
                }

                Debug.LogWarning("[Unity Resource RAG] MCP bridge warmup did not complete after retries. " + lastMessage);
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[Unity Resource RAG] Background bridge warmup failed: " + ex.Message);
            }
            finally
            {
                _bridgeWarmupScheduled = false;
            }
        }

        private static string BuildSummary(UnityResourceRagQuickSetupResult result)
        {
            if (result.Success && result.Warnings.Count == 0)
            {
                return "Quick Setup completed successfully.";
            }

            if (result.Success)
            {
                return $"Quick Setup completed with {result.Warnings.Count} warning(s).";
            }

            return $"Quick Setup failed with {result.Errors.Count} error(s).";
        }
    }
}
