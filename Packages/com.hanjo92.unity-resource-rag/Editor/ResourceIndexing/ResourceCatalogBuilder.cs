using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Builds a normalized catalog from Unity assets that are likely to participate in UI composition.
    /// </summary>
    public static class ResourceCatalogBuilder
    {
        private static readonly string[] DefaultAssetTypes =
        {
            "Sprite",
            "Texture2D",
            "Prefab",
            "TMP_FontAsset",
            "Material"
        };

        public static List<ResourceCatalogRecord> BuildCatalog(IndexProjectResourcesTool.Parameters parameters, string previewDirectory)
        {
            HashSet<string> targets = NormalizeAssetTypes(parameters.assetTypes);
            var records = new List<ResourceCatalogRecord>();

            if (targets.Contains("Sprite"))
            {
                CollectSprites(records, parameters.includePreviews, previewDirectory);
            }

            if (targets.Contains("Texture2D"))
            {
                CollectAssets(records, "Texture2D", parameters.includePreviews, previewDirectory);
            }

            if (targets.Contains("Prefab"))
            {
                CollectAssets(records, "Prefab", parameters.includePreviews, previewDirectory);
            }

            if (targets.Contains("TMP_FontAsset"))
            {
                CollectAssets(records, "TMP_FontAsset", parameters.includePreviews, previewDirectory);
            }

            if (targets.Contains("Material"))
            {
                CollectAssets(records, "Material", parameters.includePreviews, previewDirectory);
            }

            if (targets.Contains("ScriptableObject"))
            {
                CollectAssets(records, "ScriptableObject", parameters.includePreviews, previewDirectory);
            }

            return records
                .OrderBy(record => record.assetType ?? string.Empty)
                .ThenBy(record => record.path ?? string.Empty)
                .ThenBy(record => record.subAssetName ?? string.Empty)
                .ToList();
        }

        private static HashSet<string> NormalizeAssetTypes(IEnumerable<string> requestedAssetTypes)
        {
            if (requestedAssetTypes == null)
            {
                return new HashSet<string>(DefaultAssetTypes, StringComparer.OrdinalIgnoreCase);
            }

            string[] materialized = requestedAssetTypes
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .ToArray();

            if (materialized.Length == 0)
            {
                return new HashSet<string>(DefaultAssetTypes, StringComparer.OrdinalIgnoreCase);
            }

            return new HashSet<string>(materialized, StringComparer.OrdinalIgnoreCase);
        }

        private static void CollectSprites(List<ResourceCatalogRecord> records, bool includePreviews, string previewDirectory)
        {
            string[] guids = AssetDatabase.FindAssets("t:Sprite");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrWhiteSpace(path))
                {
                    continue;
                }

                UnityEngine.Object[] assetsAtPath = AssetDatabase.LoadAllAssetsAtPath(path);
                foreach (Sprite sprite in assetsAtPath.OfType<Sprite>())
                {
                    records.Add(BuildRecord(sprite, path, "Sprite", includePreviews, previewDirectory));
                }
            }
        }

        private static void CollectAssets(List<ResourceCatalogRecord> records, string assetType, bool includePreviews, string previewDirectory)
        {
            string[] guids = AssetDatabase.FindAssets("t:" + assetType);
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrWhiteSpace(path))
                {
                    continue;
                }

                UnityEngine.Object asset = AssetDatabase.LoadMainAssetAtPath(path);
                if (asset == null)
                {
                    continue;
                }

                if (asset is DefaultAsset)
                {
                    continue;
                }

                records.Add(BuildRecord(asset, path, assetType, includePreviews, previewDirectory));
            }
        }

        private static ResourceCatalogRecord BuildRecord(
            UnityEngine.Object asset,
            string path,
            string assetType,
            bool includePreviews,
            string previewDirectory)
        {
            string guid;
            long localFileId;
            if (!AssetDatabase.TryGetGUIDAndLocalFileIdentifier(asset, out guid, out localFileId))
            {
                guid = AssetDatabase.AssetPathToGUID(path);
                localFileId = 0L;
            }

            List<string> labels = AssetDatabase.GetLabels(asset)?.ToList() ?? new List<string>();
            List<string> pathTokens = Tokenize(path);
            List<string> nameTokens = Tokenize(asset.name);
            List<string> inferredTokens = InferSemanticTokens(asset, assetType);

            var record = new ResourceCatalogRecord
            {
                id = string.Format("{0}:{1}", guid, localFileId),
                guid = guid,
                localFileId = localFileId,
                path = path,
                subAssetName = asset is Sprite ? asset.name : null,
                assetType = assetType,
                name = asset.name,
                labels = labels,
                folderTokens = pathTokens,
                semanticText = BuildSemanticText(pathTokens, nameTokens, labels, inferredTokens),
                geometry = BuildGeometry(asset),
                uiHints = BuildUiHints(asset, assetType, inferredTokens),
                prefabSummary = BuildPrefabSummary(asset),
                embeddingRefs = new ResourceEmbeddingRefs
                {
                    textEmbeddingId = string.Format("{0}:{1}", guid, localFileId)
                },
                binding = new ResourceBindingInfo
                {
                    kind = InferBindingKind(assetType),
                    unityLoadPath = path,
                    subAssetName = asset is Sprite ? asset.name : null,
                    localFileId = localFileId
                },
                updatedAtUtc = DateTime.UtcNow.ToString("o")
            };

            if (includePreviews)
            {
                ResourcePreviewInfo previewInfo;
                if (ResourcePreviewExporter.TryExportPreview(asset, guid, localFileId, previewDirectory, out previewInfo))
                {
                    record.preview = previewInfo;
                    record.embeddingRefs.imageEmbeddingId = record.id;
                }
            }

            return record;
        }

        private static ResourceGeometryInfo BuildGeometry(UnityEngine.Object asset)
        {
            if (asset is Sprite sprite)
            {
                return new ResourceGeometryInfo
                {
                    width = Mathf.RoundToInt(sprite.rect.width),
                    height = Mathf.RoundToInt(sprite.rect.height),
                    aspectRatio = sprite.rect.height <= 0f ? 0f : sprite.rect.width / sprite.rect.height,
                    border = new ResourceBorderInfo
                    {
                        left = Mathf.RoundToInt(sprite.border.x),
                        bottom = Mathf.RoundToInt(sprite.border.y),
                        right = Mathf.RoundToInt(sprite.border.z),
                        top = Mathf.RoundToInt(sprite.border.w)
                    },
                    pivot = new ResourceVector2
                    {
                        x = sprite.rect.width <= 0f ? 0.5f : sprite.pivot.x / sprite.rect.width,
                        y = sprite.rect.height <= 0f ? 0.5f : sprite.pivot.y / sprite.rect.height
                    }
                };
            }

            if (asset is Texture2D texture)
            {
                return new ResourceGeometryInfo
                {
                    width = texture.width,
                    height = texture.height,
                    aspectRatio = texture.height == 0 ? 0f : (float)texture.width / texture.height,
                    pivot = new ResourceVector2 { x = 0.5f, y = 0.5f }
                };
            }

            return null;
        }

        private static ResourceUiHints BuildUiHints(UnityEngine.Object asset, string assetType, List<string> semanticTokens)
        {
            string semanticBlob = string.Join(" ", semanticTokens);
            bool looksRepeatable = ContainsAny(semanticBlob, "slot", "cell", "card", "item", "tab", "button");
            bool looksFrame = ContainsAny(semanticBlob, "frame", "panel", "popup", "modal", "window");

            return new ResourceUiHints
            {
                isNineSliceCandidate = asset is Sprite sprite && (sprite.border.x + sprite.border.y + sprite.border.z + sprite.border.w) > 0f,
                isSingleImageRegion = asset is Sprite || asset is Texture2D,
                isRepeatableBlock = assetType.Equals("Prefab", StringComparison.OrdinalIgnoreCase) && looksRepeatable,
                preferredUse = InferPreferredUse(semanticBlob, looksFrame, looksRepeatable)
            };
        }

        private static ResourcePrefabSummary BuildPrefabSummary(UnityEngine.Object asset)
        {
            GameObject prefab = asset as GameObject;
            if (prefab == null)
            {
                return null;
            }

            var componentTypes = new HashSet<string>();
            var childPaths = new List<string>();

            CollectPrefabData(prefab.transform, prefab.name, componentTypes, childPaths);

            return new ResourcePrefabSummary
            {
                rootName = prefab.name,
                componentTypes = componentTypes.OrderBy(value => value).ToList(),
                childPaths = childPaths
            };
        }

        private static void CollectPrefabData(
            Transform transform,
            string currentPath,
            HashSet<string> componentTypes,
            List<string> childPaths)
        {
            childPaths.Add(currentPath);
            Component[] components = transform.GetComponents<Component>();
            for (int i = 0; i < components.Length; i++)
            {
                Component component = components[i];
                if (component == null)
                {
                    continue;
                }

                componentTypes.Add(component.GetType().Name);
            }

            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                CollectPrefabData(child, currentPath + "/" + child.name, componentTypes, childPaths);
            }
        }

        private static List<string> InferSemanticTokens(UnityEngine.Object asset, string assetType)
        {
            var tokens = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string token in Tokenize(asset.name))
            {
                tokens.Add(token);
            }

            string typeToken = assetType.ToLowerInvariant();
            tokens.Add(typeToken);

            if (asset is GameObject prefab)
            {
                Component[] components = prefab.GetComponents<Component>();
                for (int i = 0; i < components.Length; i++)
                {
                    Component component = components[i];
                    if (component == null)
                    {
                        continue;
                    }

                    foreach (string token in Tokenize(component.GetType().Name))
                    {
                        tokens.Add(token);
                    }
                }
            }

            if (asset is Material material && material.shader != null)
            {
                foreach (string token in Tokenize(material.shader.name))
                {
                    tokens.Add(token);
                }
            }

            return tokens.OrderBy(value => value).ToList();
        }

        private static List<string> InferPreferredUse(string semanticBlob, bool looksFrame, bool looksRepeatable)
        {
            var uses = new List<string>();

            if (looksFrame)
            {
                uses.Add("panel_frame");
            }

            if (ContainsAny(semanticBlob, "popup", "modal", "dialog", "window"))
            {
                uses.Add("popup_frame");
            }

            if (ContainsAny(semanticBlob, "inventory", "slot", "item", "equipment"))
            {
                uses.Add("inventory");
            }

            if (ContainsAny(semanticBlob, "hud", "status", "actionbar", "health", "mana"))
            {
                uses.Add("hud");
            }

            if (ContainsAny(semanticBlob, "badge", "icon", "emblem"))
            {
                uses.Add("badge_icon");
            }

            if (looksRepeatable)
            {
                uses.Add("repeatable_block");
            }

            return uses.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static string BuildSemanticText(
            IEnumerable<string> pathTokens,
            IEnumerable<string> nameTokens,
            IEnumerable<string> labels,
            IEnumerable<string> inferredTokens)
        {
            var tokens = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            AddTokens(tokens, pathTokens);
            AddTokens(tokens, nameTokens);
            AddTokens(tokens, labels.SelectMany(Tokenize));
            AddTokens(tokens, inferredTokens);

            return string.Join(" ", tokens.OrderBy(value => value));
        }

        private static void AddTokens(HashSet<string> target, IEnumerable<string> values)
        {
            foreach (string value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    target.Add(value.Trim().ToLowerInvariant());
                }
            }
        }

        private static List<string> Tokenize(string input)
        {
            if (string.IsNullOrWhiteSpace(input))
            {
                return new List<string>();
            }

            string normalized = Regex.Replace(input, "([a-z0-9])([A-Z])", "$1 $2");
            normalized = Regex.Replace(normalized, "[^A-Za-z0-9]+", " ");
            return normalized
                .ToLowerInvariant()
                .Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries)
                .Distinct()
                .ToList();
        }

        private static bool ContainsAny(string source, params string[] values)
        {
            for (int i = 0; i < values.Length; i++)
            {
                if (source.IndexOf(values[i], StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return true;
                }
            }

            return false;
        }

        private static string InferBindingKind(string assetType)
        {
            switch (assetType)
            {
                case "Sprite":
                    return "sprite";
                case "Texture2D":
                    return "texture";
                case "Prefab":
                    return "prefab";
                case "TMP_FontAsset":
                    return "tmp_font";
                case "Material":
                    return "material";
                default:
                    return "scriptable_object";
            }
        }
    }
}
