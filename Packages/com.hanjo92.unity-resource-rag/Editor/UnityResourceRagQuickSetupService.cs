using System;
using System.Collections.Generic;
using System.Threading;
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
            bool started = server.StartLocalHttpServer(true);
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
            result.Steps.Add($"Python interpreter: {settings.PythonExecutable}");

            if (settings.AuthMode == UnityResourceRagAuthMode.UseExistingCodexLogin)
            {
                if (settings.HasReadableCodexAuthFile)
                {
                    result.Steps.Add($"Found the Codex auth file: {settings.CodexAuthFile}");
                }
                else
                {
                    result.Warnings.Add("The Codex auth file was not found. The build can still continue with `recommended_auto` or local fallback, but OpenAI calls may fail.");
                }
                return;
            }

            if (settings.AuthMode == UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable)
            {
                string envName = settings.ProviderApiKeyEnv;
                if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(envName)))
                {
                    result.Warnings.Add($"The environment variable `{envName}` is currently empty.");
                }
                else
                {
                    result.Steps.Add($"Prepared to use the API key environment variable `{envName}`.");
                }
                return;
            }

            result.Steps.Add("Configured the window to use Offline local fallback mode.");
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
            try
            {
                bool started = await MCPServiceLocator.Bridge.StartAsync();
                if (!started)
                {
                    Debug.LogWarning("[Unity Resource RAG] MCP bridge start did not complete. If tools stay unavailable, press Start Bridge once in the Unity MCP window.");
                    return;
                }

                BridgeVerificationResult verification = await MCPServiceLocator.Bridge.VerifyAsync();
                if (verification.Success)
                {
                    Debug.Log("[Unity Resource RAG] MCP bridge warmup completed successfully.");
                }
                else
                {
                    Debug.LogWarning("[Unity Resource RAG] MCP bridge started, but verification is incomplete: " + verification.Message);
                }
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
