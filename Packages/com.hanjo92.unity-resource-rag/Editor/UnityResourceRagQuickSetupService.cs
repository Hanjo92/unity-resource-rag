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

            result.Steps.Add($"Unity MCP를 HTTP Local (`{settings.UnityMcpBaseUrl}`)로 고정했습니다.");
            result.Steps.Add("Project Scoped Tools를 꺼서 custom tool이 직접 노출되도록 맞췄습니다.");
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
                    result.Steps.Add($"custom tool `{toolName}` 를 활성화했습니다.");
                    break;
                }

                if (!found)
                {
                    result.Warnings.Add($"custom tool `{toolName}` 를 아직 발견하지 못했습니다. Unity 컴파일이 끝난 뒤 창을 다시 열어주세요.");
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
                    result.Steps.Add($"resource `{resourceName}` 를 활성화했습니다.");
                    break;
                }

                if (!found)
                {
                    result.Warnings.Add($"resource `{resourceName}` 를 아직 발견하지 못했습니다. Unity 컴파일이 끝났는지 확인해 주세요.");
                }
            }
        }

        private static void RestartServerAndBridge(UnityResourceRagQuickSetupResult result)
        {
            IServerManagementService server = MCPServiceLocator.Server;
            if (!server.CanStartLocalServer())
            {
                result.Errors.Add("Unity MCP Local HTTP Server를 시작할 수 없습니다. HTTP Local 설정을 다시 확인해 주세요.");
                return;
            }

            server.StopManagedLocalHttpServer();
            bool started = server.StartLocalHttpServer(true);
            if (!started && !server.IsLocalHttpServerReachable())
            {
                result.Errors.Add("Unity MCP Local HTTP Server 시작에 실패했습니다.");
                return;
            }

            WaitFor(server.IsLocalHttpServerReachable, 3000);
            result.Steps.Add("Unity MCP Local HTTP Server를 재시작했습니다.");
            ScheduleBridgeWarmup();
            result.Steps.Add("MCP bridge 시작을 백그라운드로 예약했습니다.");
            result.Warnings.Add("bridge warmup은 비동기로 이어집니다. Quick Setup 직후에는 Unity Console 또는 Unity MCP 창 상태를 함께 확인해 주세요.");
        }

        private static void CheckAuthMode(UnityResourceRagEditorSettings settings, UnityResourceRagQuickSetupResult result)
        {
            result.Steps.Add($"Python interpreter: {settings.PythonExecutable}");

            if (settings.AuthMode == UnityResourceRagAuthMode.UseExistingCodexLogin)
            {
                if (settings.HasReadableCodexAuthFile)
                {
                    result.Steps.Add($"Codex 로그인 파일을 찾았습니다: {settings.CodexAuthFile}");
                }
                else
                {
                    result.Warnings.Add("Codex 로그인 파일을 찾지 못했습니다. build는 `recommended_auto` 또는 local fallback으로 계속 시도되지만, OpenAI 호출은 실패할 수 있습니다.");
                }
                return;
            }

            if (settings.AuthMode == UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable)
            {
                string envName = settings.ProviderApiKeyEnv;
                if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(envName)))
                {
                    result.Warnings.Add($"환경 변수 `{envName}` 가 현재 비어 있습니다.");
                }
                else
                {
                    result.Steps.Add($"API key 환경 변수 `{envName}` 를 사용하도록 준비했습니다.");
                }
                return;
            }

            result.Steps.Add("offline local fallback 모드로 설정했습니다.");
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
