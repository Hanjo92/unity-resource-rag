using System;
using System.Collections.Generic;
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
        private static readonly Dictionary<string, ResolvedAssetCacheEntry> ResolvedAssetCache = new Dictionary<string, ResolvedAssetCacheEntry>(StringComparer.Ordinal);
        private static readonly Dictionary<string, UnityEngine.Object[]> SubAssetCache = new Dictionary<string, UnityEngine.Object[]>(StringComparer.Ordinal);
        private static readonly Dictionary<string, UnityEngine.Object> PrimaryAssetCache = new Dictionary<string, UnityEngine.Object>(StringComparer.Ordinal);
        private static readonly Dictionary<string, Type> TypeCache = new Dictionary<string, Type>(StringComparer.Ordinal);

        private sealed class ResolvedAssetCacheEntry
        {
            public string AssetPath { get; set; }
            public UnityEngine.Object Asset { get; set; }
        }

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

            string cacheKey = BuildReferenceCacheKey(reference);
            if (ResolvedAssetCache.TryGetValue(cacheKey, out ResolvedAssetCacheEntry cachedEntry) && cachedEntry != null)
            {
                if (cachedEntry.Asset != null)
                {
                    asset = cachedEntry.Asset;
                    assetPath = cachedEntry.AssetPath;
                    return true;
                }

                ResolvedAssetCache.Remove(cacheKey);
            }

            assetPath = ResolveAssetPath(reference);
            if (string.IsNullOrWhiteSpace(assetPath))
            {
                error = "Could not resolve asset path from blueprint reference.";
                return false;
            }

            if (!string.IsNullOrWhiteSpace(reference.subAssetName) || (reference.localFileId.HasValue && reference.localFileId.Value != 0))
            {
                UnityEngine.Object[] subAssets = LoadSubAssets(assetPath);
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

            ResolvedAssetCache[cacheKey] = new ResolvedAssetCacheEntry
            {
                AssetPath = assetPath,
                Asset = asset
            };
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

        private static string BuildReferenceCacheKey(UiAssetReference reference)
        {
            return string.Join(
                "|",
                reference.kind ?? string.Empty,
                reference.guid ?? string.Empty,
                reference.path ?? string.Empty,
                reference.localFileId?.ToString() ?? string.Empty,
                reference.subAssetName ?? string.Empty);
        }

        private static UnityEngine.Object[] LoadSubAssets(string assetPath)
        {
            if (string.IsNullOrWhiteSpace(assetPath))
            {
                return Array.Empty<UnityEngine.Object>();
            }

            if (SubAssetCache.TryGetValue(assetPath, out UnityEngine.Object[] cachedAssets))
            {
                if (cachedAssets != null && cachedAssets.Any(candidate => candidate != null))
                {
                    return cachedAssets;
                }

                SubAssetCache.Remove(assetPath);
            }

            UnityEngine.Object[] loadedAssets = AssetDatabase.LoadAllAssetsAtPath(assetPath) ?? Array.Empty<UnityEngine.Object>();
            SubAssetCache[assetPath] = loadedAssets;
            return loadedAssets;
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
            string cacheKey = string.Concat(kind ?? string.Empty, "|", assetPath ?? string.Empty);
            if (PrimaryAssetCache.TryGetValue(cacheKey, out UnityEngine.Object cachedAsset))
            {
                if (cachedAsset != null)
                {
                    return cachedAsset;
                }

                PrimaryAssetCache.Remove(cacheKey);
            }

            UnityEngine.Object resolvedAsset = null;
            if (string.Equals(kind, "sprite", StringComparison.OrdinalIgnoreCase))
            {
                Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
                if (sprite != null)
                {
                    resolvedAsset = sprite;
                }
            }

            if (resolvedAsset == null && string.Equals(kind, "prefab", StringComparison.OrdinalIgnoreCase))
            {
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                if (prefab != null)
                {
                    resolvedAsset = prefab;
                }
            }

            if (resolvedAsset == null && string.Equals(kind, "tmp_font", StringComparison.OrdinalIgnoreCase))
            {
                Type tmpFontType = ResolveType("TMPro.TMP_FontAsset");
                if (tmpFontType != null)
                {
                    UnityEngine.Object font = AssetDatabase.LoadAssetAtPath(assetPath, tmpFontType);
                    if (font != null)
                    {
                        resolvedAsset = font;
                    }
                }
            }

            if (resolvedAsset == null)
            {
                resolvedAsset = AssetDatabase.LoadMainAssetAtPath(assetPath);
            }

            if (resolvedAsset != null)
            {
                PrimaryAssetCache[cacheKey] = resolvedAsset;
            }

            return resolvedAsset;
        }

        private static Type ResolveType(string typeName)
        {
            if (string.IsNullOrWhiteSpace(typeName))
            {
                return null;
            }

            if (TypeCache.TryGetValue(typeName, out Type cachedType))
            {
                return cachedType;
            }

            Type resolved = Type.GetType(typeName);
            if (resolved != null)
            {
                TypeCache[typeName] = resolved;
                return resolved;
            }

            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                resolved = assembly.GetType(typeName);
                if (resolved != null)
                {
                    TypeCache[typeName] = resolved;
                    return resolved;
                }
            }

            TypeCache[typeName] = null;
            return null;
        }
    }
}
