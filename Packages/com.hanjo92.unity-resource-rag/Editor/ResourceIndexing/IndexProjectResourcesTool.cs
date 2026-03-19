using System;
using System.Collections.Generic;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Builds an external JSONL catalog from Unity UI-related assets so a sidecar vector pipeline can index them.
    /// </summary>
    [McpForUnityTool(
        "index_project_resources",
        Description = "Scan Unity UI-related project assets and export a normalized JSONL catalog plus optional previews for asset-aware UI retrieval."
    )]
    public static class IndexProjectResourcesTool
    {
        public sealed class Parameters
        {
            [ToolParameter("Project-relative or absolute output path for the JSONL catalog.", Required = false, DefaultValue = ResourceCatalogStorage.DefaultCatalogRelativePath)]
            public string outputPath { get; set; }

            [ToolParameter("Project-relative or absolute output path for the manifest JSON.", Required = false, DefaultValue = ResourceCatalogStorage.DefaultManifestRelativePath)]
            public string manifestPath { get; set; }

            [ToolParameter("Project-relative or absolute preview directory for exported PNG previews.", Required = false, DefaultValue = ResourceCatalogStorage.DefaultPreviewRelativePath)]
            public string previewDirectory { get; set; }

            [ToolParameter("Whether to export preview PNG files alongside the catalog.", Required = false, DefaultValue = "true")]
            public bool includePreviews { get; set; } = true;

            [ToolParameter("Asset types to include. Examples: Sprite, Texture2D, Prefab, TMP_FontAsset, Material, ScriptableObject.", Required = false)]
            public List<string> assetTypes { get; set; }
        }

        public static object HandleCommand(JObject @params)
        {
            try
            {
                Parameters parameters = @params == null
                    ? new Parameters()
                    : @params.ToObject<Parameters>() ?? new Parameters();

                string catalogPath = ResourceCatalogStorage.ResolveProjectPath(
                    parameters.outputPath,
                    ResourceCatalogStorage.DefaultCatalogRelativePath);
                string manifestPath = ResourceCatalogStorage.ResolveProjectPath(
                    parameters.manifestPath,
                    ResourceCatalogStorage.DefaultManifestRelativePath);
                string previewDirectory = ResourceCatalogStorage.ResolveProjectPath(
                    parameters.previewDirectory,
                    ResourceCatalogStorage.DefaultPreviewRelativePath);

                List<ResourceCatalogRecord> records = ResourceCatalogBuilder.BuildCatalog(parameters, previewDirectory);
                ResourceCatalogManifest manifest = ResourceCatalogStorage.WriteCatalog(
                    records,
                    catalogPath,
                    manifestPath,
                    previewDirectory);

                return new SuccessResponse(
                    "Indexed project resources successfully.",
                    new
                    {
                        catalogPath = manifest.catalogPath,
                        manifestPath,
                        previewDirectory = manifest.previewDirectory,
                        recordCount = manifest.recordCount,
                        assetCounts = manifest.assetCounts
                    });
            }
            catch (Exception ex)
            {
                return new ErrorResponse("Failed to index project resources: " + ex.Message);
            }
        }
    }
}
