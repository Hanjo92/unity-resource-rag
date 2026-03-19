using System;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Resolves assets from blueprint references using GUID, path, local file id, and sub-asset name.
    /// </summary>
    public static class UnityAssetResolver
    {
        public static bool TryResolve(UiAssetReference reference, out UnityEngine.Object asset, out string assetPath, out string error)
        {
            asset = null;
            assetPath = null;
            error = null;

            if (reference == null)
            {
                error = "Asset reference is missing.";
                return false;
            }

            assetPath = ResolveAssetPath(reference);
            if (string.IsNullOrWhiteSpace(assetPath))
            {
                error = "Could not resolve asset path from blueprint reference.";
                return false;
            }

            if (!string.IsNullOrWhiteSpace(reference.subAssetName) || (reference.localFileId.HasValue && reference.localFileId.Value != 0))
            {
                UnityEngine.Object[] subAssets = AssetDatabase.LoadAllAssetsAtPath(assetPath);
                asset = subAssets.FirstOrDefault(candidate => MatchesSubAsset(candidate, reference));
            }

            if (asset == null)
            {
                asset = LoadPrimaryAsset(assetPath, reference.kind);
            }

            if (asset == null)
            {
                error = $"Asset could not be loaded from '{assetPath}'.";
                return false;
            }

            return true;
        }

        public static bool TryResolveSprite(UiAssetReference reference, out Sprite sprite, out string assetPath, out string error)
        {
            sprite = null;
            if (!TryResolve(reference, out var asset, out assetPath, out error))
            {
                return false;
            }

            sprite = asset as Sprite;
            if (sprite == null && asset is Texture2D)
            {
                sprite = AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
            }

            if (sprite == null)
            {
                error = $"Resolved asset at '{assetPath}' is not a Sprite.";
                return false;
            }

            return true;
        }

        public static bool TryResolvePrefab(UiAssetReference reference, out GameObject prefab, out string assetPath, out string error)
        {
            prefab = null;
            if (!TryResolve(reference, out var asset, out assetPath, out error))
            {
                return false;
            }

            prefab = asset as GameObject;
            if (prefab == null)
            {
                error = $"Resolved asset at '{assetPath}' is not a Prefab/GameObject.";
                return false;
            }

            return true;
        }

        public static bool TryResolveTmpFont(UiAssetReference reference, out UnityEngine.Object fontAsset, out string assetPath, out string error)
        {
            fontAsset = null;
            if (!TryResolve(reference, out var asset, out assetPath, out error))
            {
                return false;
            }

            Type tmpFontType = ResolveType("TMPro.TMP_FontAsset");
            if (tmpFontType == null)
            {
                error = "TMPro.TMP_FontAsset could not be resolved.";
                return false;
            }

            if (!tmpFontType.IsInstanceOfType(asset))
            {
                error = $"Resolved asset at '{assetPath}' is not a TMP_FontAsset.";
                return false;
            }

            fontAsset = asset;
            return true;
        }

        private static string ResolveAssetPath(UiAssetReference reference)
        {
            if (!string.IsNullOrWhiteSpace(reference.path))
            {
                return reference.path;
            }

            if (!string.IsNullOrWhiteSpace(reference.guid))
            {
                return AssetDatabase.GUIDToAssetPath(reference.guid);
            }

            return null;
        }

        private static bool MatchesSubAsset(UnityEngine.Object candidate, UiAssetReference reference)
        {
            if (candidate == null)
            {
                return false;
            }

            if (!string.IsNullOrWhiteSpace(reference.subAssetName) &&
                string.Equals(candidate.name, reference.subAssetName, StringComparison.Ordinal))
            {
                return true;
            }

            if (reference.localFileId.HasValue && reference.localFileId.Value != 0)
            {
                string candidateGuid;
                long candidateLocalFileId;
                if (AssetDatabase.TryGetGUIDAndLocalFileIdentifier(candidate, out candidateGuid, out candidateLocalFileId) &&
                    candidateLocalFileId == reference.localFileId.Value)
                {
                    return true;
                }
            }

            return false;
        }

        private static UnityEngine.Object LoadPrimaryAsset(string assetPath, string kind)
        {
            if (string.Equals(kind, "sprite", StringComparison.OrdinalIgnoreCase))
            {
                Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
                if (sprite != null)
                {
                    return sprite;
                }
            }

            if (string.Equals(kind, "prefab", StringComparison.OrdinalIgnoreCase))
            {
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                if (prefab != null)
                {
                    return prefab;
                }
            }

            if (string.Equals(kind, "tmp_font", StringComparison.OrdinalIgnoreCase))
            {
                Type tmpFontType = ResolveType("TMPro.TMP_FontAsset");
                if (tmpFontType != null)
                {
                    UnityEngine.Object font = AssetDatabase.LoadAssetAtPath(assetPath, tmpFontType);
                    if (font != null)
                    {
                        return font;
                    }
                }
            }

            return AssetDatabase.LoadMainAssetAtPath(assetPath);
        }

        private static Type ResolveType(string typeName)
        {
            Type resolved = Type.GetType(typeName);
            if (resolved != null)
            {
                return resolved;
            }

            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                resolved = assembly.GetType(typeName);
                if (resolved != null)
                {
                    return resolved;
                }
            }

            return null;
        }
    }
}
