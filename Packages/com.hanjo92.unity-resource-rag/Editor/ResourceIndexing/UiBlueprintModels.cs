using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Root document for a deterministic UI assembly plan.
    /// </summary>
    [Serializable]
    public sealed class UiBlueprintDocument
    {
        public string screenName { get; set; }
        public string stack { get; set; }
        public UiBlueprintNode root { get; set; }
    }

    [Serializable]
    public sealed class UiBlueprintNode
    {
        public string id { get; set; }
        public string name { get; set; }
        public string kind { get; set; }
        public bool active { get; set; } = true;
        public UiRectTransformSpec rect { get; set; }
        public UiCanvasScalerSpec canvasScaler { get; set; }
        public UiAssetReference asset { get; set; }
        public UiImageSpec image { get; set; }
        public UiTmpTextSpec text { get; set; }
        public UiLayoutGroupSpec layoutGroup { get; set; }
        public UiLayoutElementSpec layoutElement { get; set; }
        public List<UiCustomComponentSpec> components { get; set; } = new List<UiCustomComponentSpec>();
        public List<UiBlueprintNode> children { get; set; } = new List<UiBlueprintNode>();
    }

    [Serializable]
    public sealed class UiRectTransformSpec
    {
        public UiFloat2 anchorMin { get; set; }
        public UiFloat2 anchorMax { get; set; }
        public UiFloat2 pivot { get; set; }
        public UiFloat2 anchoredPosition { get; set; }
        public UiFloat2 sizeDelta { get; set; }
        public UiFloat2 offsetMin { get; set; }
        public UiFloat2 offsetMax { get; set; }
    }

    [Serializable]
    public sealed class UiCanvasScalerSpec
    {
        public string uiScaleMode { get; set; } = "ScaleWithScreenSize";
        public UiInt2 referenceResolution { get; set; }
        public string screenMatchMode { get; set; } = "MatchWidthOrHeight";
        public float? matchWidthOrHeight { get; set; }
    }

    [Serializable]
    public sealed class UiImageSpec
    {
        public string type { get; set; } = "Simple";
        public bool? preserveAspect { get; set; }
        public bool? raycastTarget { get; set; }
        public string color { get; set; }
    }

    [Serializable]
    public sealed class UiTmpTextSpec
    {
        public string value { get; set; }
        public UiAssetReference fontAsset { get; set; }
        public float? fontSize { get; set; }
        public bool? enableAutoSizing { get; set; }
        public bool? raycastTarget { get; set; }
        public string alignment { get; set; }
        public string color { get; set; }
    }

    [Serializable]
    public sealed class UiLayoutGroupSpec
    {
        public string kind { get; set; }
        public UiPaddingSpec padding { get; set; }
        public string childAlignment { get; set; }
        public float? spacing { get; set; }
        public UiFloat2 spacing2 { get; set; }
        public bool? childControlWidth { get; set; }
        public bool? childControlHeight { get; set; }
        public bool? childForceExpandWidth { get; set; }
        public bool? childForceExpandHeight { get; set; }
        public bool? childScaleWidth { get; set; }
        public bool? childScaleHeight { get; set; }
        public UiFloat2 cellSize { get; set; }
        public string constraint { get; set; }
        public int? constraintCount { get; set; }
        public string startCorner { get; set; }
        public string startAxis { get; set; }
    }

    [Serializable]
    public sealed class UiLayoutElementSpec
    {
        public float? minWidth { get; set; }
        public float? minHeight { get; set; }
        public float? preferredWidth { get; set; }
        public float? preferredHeight { get; set; }
        public float? flexibleWidth { get; set; }
        public float? flexibleHeight { get; set; }
        public bool? ignoreLayout { get; set; }
    }

    [Serializable]
    public sealed class UiPaddingSpec
    {
        public int left { get; set; }
        public int right { get; set; }
        public int top { get; set; }
        public int bottom { get; set; }
    }

    [Serializable]
    public sealed class UiCustomComponentSpec
    {
        public string typeName { get; set; }
        public JObject properties { get; set; }
    }

    [Serializable]
    public sealed class UiAssetReference
    {
        public string kind { get; set; }
        public string path { get; set; }
        public string guid { get; set; }
        public long? localFileId { get; set; }
        public string subAssetName { get; set; }
    }

    [Serializable]
    public sealed class UiFloat2
    {
        public float x { get; set; }
        public float y { get; set; }
    }

    [Serializable]
    public sealed class UiInt2
    {
        public int x { get; set; }
        public int y { get; set; }
    }

    [Serializable]
    public sealed class UiBlueprintIssue
    {
        public string severity { get; set; }
        public string nodeId { get; set; }
        public string nodeName { get; set; }
        public string message { get; set; }
    }

    [Serializable]
    public sealed class UiBlueprintApplyResult
    {
        public string nodeId { get; set; }
        public string nodeName { get; set; }
        public string kind { get; set; }
        public string hierarchyPath { get; set; }
        public int instanceId { get; set; }
        public string assetPath { get; set; }
    }

    [Serializable]
    public sealed class UiBlueprintVerificationHint
    {
        public string tool { get; set; }
        public object parameters { get; set; }
    }
}
