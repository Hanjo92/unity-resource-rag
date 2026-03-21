using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Tool wrapper for clients that handle tools better than MCP resources.
    /// </summary>
    [McpForUnityTool(
        "query_ui_asset_catalog",
        Description = "Read the exported UI asset catalog as a paged tool result. Use this when the MCP client is better at tools than resources."
    )]
    public static class QueryUiAssetCatalogTool
    {
        public sealed class Parameters
        {
            [ToolParameter("Project-relative or absolute path to resource_catalog.jsonl.", Required = false, DefaultValue = ResourceCatalogStorage.DefaultCatalogRelativePath)]
            public string catalogPath { get; set; }

            [ToolParameter("Optional asset type filter. Examples: Sprite, Prefab, TMP_FontAsset, Material.", Required = false)]
            public string assetType { get; set; }

            [ToolParameter("Optional name/path query filter.", Required = false)]
            public string query { get; set; }

            [ToolParameter("How many items to return per page.", Required = false, DefaultValue = "25")]
            public int pageSize { get; set; } = 25;

            [ToolParameter("1-based page number.", Required = false, DefaultValue = "1")]
            public int pageNumber { get; set; } = 1;
        }

        public static object HandleCommand(JObject @params)
        {
            Parameters parameters = @params == null
                ? new Parameters()
                : @params.ToObject<Parameters>() ?? new Parameters();

            return UiAssetCatalogResource.HandleCommand(
                JObject.FromObject(
                    new
                    {
                        parameters.catalogPath,
                        parameters.assetType,
                        parameters.query,
                        parameters.pageSize,
                        parameters.pageNumber
                    }));
        }
    }
}
