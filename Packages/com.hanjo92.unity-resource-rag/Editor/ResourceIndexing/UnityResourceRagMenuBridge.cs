using System;
using System.IO;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Unity MCP 커스텀 툴이 직접 노출되지 않을 때를 위한 메뉴 기반 우회 브리지입니다.
    /// </summary>
    public static class UnityResourceRagMenuBridge
    {
        public const string ExecuteMenuPath = "Tools/Unity Resource RAG/Interop/대기 요청 실행";
        private const string RequestRelativePath = "Library/ResourceRag/Interop/menu_tool_request.json";
        private const string ResponseRelativePath = "Library/ResourceRag/Interop/menu_tool_response.json";

        [Serializable]
        private sealed class MenuBridgeRequest
        {
            public string requestId;
            public string toolName;
            public JObject parameters;
        }

        [Serializable]
        private sealed class MenuBridgeResponse
        {
            public string requestId;
            public string toolName;
            public bool success;
            public string error;
            public JToken payload;
            public string completedAtUtc;
        }

        [MenuItem(ExecuteMenuPath)]
        public static void ExecutePendingRequest()
        {
            MenuBridgeRequest request = null;

            try
            {
                string requestPath = GetRequestPath();
                if (!File.Exists(requestPath))
                {
                    WriteResponse(new MenuBridgeResponse
                    {
                        success = false,
                        error = "대기 중인 요청 파일이 없습니다.",
                        completedAtUtc = DateTime.UtcNow.ToString("O")
                    });
                    return;
                }

                request = JsonConvert.DeserializeObject<MenuBridgeRequest>(File.ReadAllText(requestPath));
                if (request == null)
                {
                    throw new InvalidOperationException("요청 파일을 역직렬화할 수 없습니다.");
                }

                object result = RunTool(request.toolName, request.parameters ?? new JObject());
                WriteResponse(new MenuBridgeResponse
                {
                    requestId = request.requestId,
                    toolName = request.toolName,
                    success = true,
                    payload = result == null ? JValue.CreateNull() : JToken.FromObject(result),
                    completedAtUtc = DateTime.UtcNow.ToString("O")
                });
            }
            catch (Exception ex)
            {
                Debug.LogError("[Unity Resource RAG] 메뉴 브리지 실행 실패: " + ex);
                WriteResponse(new MenuBridgeResponse
                {
                    requestId = request?.requestId,
                    toolName = request?.toolName,
                    success = false,
                    error = ex.ToString(),
                    completedAtUtc = DateTime.UtcNow.ToString("O")
                });
            }
        }

        private static object RunTool(string toolName, JObject parameters)
        {
            switch (toolName)
            {
                case "index_project_resources":
                    return IndexProjectResourcesTool.HandleCommand(parameters);
                case "apply_ui_blueprint":
                    return ApplyUiBlueprintTool.HandleCommand(parameters);
                case "query_ui_asset_catalog":
                    return QueryUiAssetCatalogTool.HandleCommand(parameters);
                default:
                    return new ErrorResponse("지원하지 않는 메뉴 브리지 툴입니다: " + toolName);
            }
        }

        private static void WriteResponse(MenuBridgeResponse response)
        {
            string responsePath = GetResponsePath();
            Directory.CreateDirectory(Path.GetDirectoryName(responsePath) ?? ProjectRootPath);
            File.WriteAllText(responsePath, JsonConvert.SerializeObject(response, Formatting.Indented));
            AssetDatabase.Refresh();
        }

        private static string GetRequestPath()
        {
            return Path.Combine(ProjectRootPath, RequestRelativePath);
        }

        private static string GetResponsePath()
        {
            return Path.Combine(ProjectRootPath, ResponseRelativePath);
        }

        private static string ProjectRootPath => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
    }
}
