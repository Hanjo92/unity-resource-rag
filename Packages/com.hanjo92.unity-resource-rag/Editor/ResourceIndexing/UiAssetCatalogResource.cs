using System;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Resources;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Exposes the latest exported asset catalog in a paged, MCP-readable form.
    /// </summary>
    [McpForUnityResource("ui_asset_catalog")]
    public static class UiAssetCatalogResource
    {
        public static object HandleCommand(JObject @params)
        {
            try
            {
                string requestedCatalogPath = @params?["catalogPath"]?.ToString();
                string assetType = @params?["assetType"]?.ToString();
                string query = @params?["query"]?.ToString();
                int pageSize = @params?["pageSize"]?.ToObject<int?>() ?? 25;
                int pageNumber = @params?["pageNumber"]?.ToObject<int?>() ?? 1;

                string catalogPath = ResourceCatalogStorage.ResolveProjectPath(
                    requestedCatalogPath,
                    ResourceCatalogStorage.DefaultCatalogRelativePath);

                var success = ResourceCatalogStorage.TryReadCatalogPage(
                    catalogPath,
                    assetType,
                    query,
                    pageSize,
                    pageNumber,
                    out var page,
                    out var totalCount,
                    out var error);

                if (!success)
                {
                    return new ErrorResponse(error);
                }

                return new SuccessResponse(
                    "Retrieved UI asset catalog page.",
                    new
                    {
                        catalogPath,
                        assetType,
                        query,
                        pageSize,
                        pageNumber,
                        totalCount,
                        items = page
                    });
            }
            catch (Exception ex)
            {
                return new ErrorResponse("Failed to read UI asset catalog: " + ex.Message);
            }
        }
    }
}
