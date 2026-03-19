using System;
using System.Collections.Generic;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// One normalized resource record that can be serialized into the external catalog.
    /// </summary>
    [Serializable]
    public sealed class ResourceCatalogRecord
    {
        public string id { get; set; }
        public string guid { get; set; }
        public long localFileId { get; set; }
        public string path { get; set; }
        public string subAssetName { get; set; }
        public string assetType { get; set; }
        public string name { get; set; }
        public List<string> labels { get; set; } = new List<string>();
        public List<string> folderTokens { get; set; } = new List<string>();
        public string semanticText { get; set; }
        public ResourcePreviewInfo preview { get; set; }
        public ResourceGeometryInfo geometry { get; set; }
        public ResourceUiHints uiHints { get; set; } = new ResourceUiHints();
        public ResourcePrefabSummary prefabSummary { get; set; }
        public ResourceEmbeddingRefs embeddingRefs { get; set; } = new ResourceEmbeddingRefs();
        public ResourceBindingInfo binding { get; set; } = new ResourceBindingInfo();
        public string updatedAtUtc { get; set; }
    }

    [Serializable]
    public sealed class ResourcePreviewInfo
    {
        public string path { get; set; }
        public int width { get; set; }
        public int height { get; set; }
    }

    [Serializable]
    public sealed class ResourceGeometryInfo
    {
        public int width { get; set; }
        public int height { get; set; }
        public float aspectRatio { get; set; }
        public ResourceBorderInfo border { get; set; }
        public ResourceVector2 pivot { get; set; }
    }

    [Serializable]
    public sealed class ResourceBorderInfo
    {
        public int left { get; set; }
        public int right { get; set; }
        public int top { get; set; }
        public int bottom { get; set; }
    }

    [Serializable]
    public sealed class ResourceVector2
    {
        public float x { get; set; }
        public float y { get; set; }
    }

    [Serializable]
    public sealed class ResourceUiHints
    {
        public bool isNineSliceCandidate { get; set; }
        public bool isSingleImageRegion { get; set; }
        public bool isRepeatableBlock { get; set; }
        public List<string> preferredUse { get; set; } = new List<string>();
    }

    [Serializable]
    public sealed class ResourcePrefabSummary
    {
        public string rootName { get; set; }
        public List<string> componentTypes { get; set; } = new List<string>();
        public List<string> childPaths { get; set; } = new List<string>();
    }

    [Serializable]
    public sealed class ResourceEmbeddingRefs
    {
        public string imageEmbeddingId { get; set; }
        public string textEmbeddingId { get; set; }
    }

    [Serializable]
    public sealed class ResourceBindingInfo
    {
        public string kind { get; set; }
        public string unityLoadPath { get; set; }
        public string subAssetName { get; set; }
        public long localFileId { get; set; }
    }

    [Serializable]
    public sealed class ResourceCatalogManifest
    {
        public string generatedAtUtc { get; set; }
        public string catalogPath { get; set; }
        public string previewDirectory { get; set; }
        public int recordCount { get; set; }
        public Dictionary<string, int> assetCounts { get; set; } = new Dictionary<string, int>();
    }
}
