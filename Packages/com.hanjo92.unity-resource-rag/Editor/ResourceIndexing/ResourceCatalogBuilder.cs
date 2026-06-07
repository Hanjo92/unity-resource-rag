using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
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
        private static readonly Dictionary<string, PropertyInfo> ComponentPropertyCache = new Dictionary<string, PropertyInfo>(StringComparer.Ordinal);
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
            UnityEngine.Object mainAsset = AssetDatabase.LoadMainAssetAtPath(path);
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
            ResourceAssetProvenance assetProvenance = BuildAssetProvenance(path, mainAsset);
            ResourceTextureSummary textureSummary = BuildTextureSummary(asset, path, mainAsset);
            ResourceMaterialSummary materialSummary = BuildMaterialSummary(asset);
            ResourcePrefabSummary prefabSummary = BuildPrefabSummary(asset);
            List<string> metadataTokens = BuildMetadataTokens(assetType, assetProvenance, textureSummary, materialSummary, prefabSummary);

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
                metadataTokens = metadataTokens,
                semanticText = BuildSemanticText(pathTokens, nameTokens, labels, inferredTokens.Concat(metadataTokens)),
                geometry = BuildGeometry(asset),
                uiHints = BuildUiHints(asset, assetType, inferredTokens, textureSummary, materialSummary, prefabSummary),
                assetProvenance = assetProvenance,
                textureSummary = textureSummary,
                materialSummary = materialSummary,
                prefabSummary = prefabSummary,
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

        private static ResourceAssetProvenance BuildAssetProvenance(string path, UnityEngine.Object mainAsset)
        {
            AssetImporter importer = AssetImporter.GetAtPath(path);
            return new ResourceAssetProvenance
            {
                mainAssetPath = path,
                mainAssetName = mainAsset != null ? mainAsset.name : null,
                mainAssetType = mainAsset != null ? mainAsset.GetType().Name : null,
                importerType = importer != null ? importer.GetType().Name : null
            };
        }

        private static ResourceTextureSummary BuildTextureSummary(UnityEngine.Object asset, string path, UnityEngine.Object mainAsset)
        {
            Texture2D texture = null;
            float? pixelsPerUnit = null;
            if (asset is Sprite sprite)
            {
                texture = sprite.texture;
                pixelsPerUnit = sprite.pixelsPerUnit;
            }
            else if (asset is Texture2D directTexture)
            {
                texture = directTexture;
            }

            if (texture == null)
            {
                return null;
            }

            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            string texturePath = AssetDatabase.GetAssetPath(texture);
            return new ResourceTextureSummary
            {
                sourceTexturePath = string.IsNullOrWhiteSpace(texturePath) ? path : texturePath,
                sourceTextureName = texture.name,
                sourceTextureAssetType = mainAsset != null ? mainAsset.GetType().Name : texture.GetType().Name,
                textureImporterType = importer != null ? importer.textureType.ToString() : null,
                spriteImportMode = importer != null ? importer.spriteImportMode.ToString() : null,
                textureFormat = texture.format.ToString(),
                wrapMode = texture.wrapMode.ToString(),
                filterMode = texture.filterMode.ToString(),
                hasAlpha = TextureFormatIncludesAlpha(texture.format),
                alphaIsTransparency = importer != null ? (bool?)importer.alphaIsTransparency : null,
                sRgbTexture = importer != null ? (bool?)importer.sRGBTexture : null,
                mipmapEnabled = importer != null ? (bool?)importer.mipmapEnabled : null,
                isReadable = texture.isReadable,
                pixelsPerUnit = pixelsPerUnit
            };
        }

        private static ResourceMaterialSummary BuildMaterialSummary(UnityEngine.Object asset)
        {
            Material material = asset as Material;
            if (material == null)
            {
                return null;
            }

            Texture mainTexture = material.mainTexture;
            string mainTexturePath = mainTexture != null ? AssetDatabase.GetAssetPath(mainTexture) : null;
            return new ResourceMaterialSummary
            {
                shaderName = material.shader != null ? material.shader.name : null,
                mainTexturePath = string.IsNullOrWhiteSpace(mainTexturePath) ? null : mainTexturePath,
                mainTextureName = mainTexture != null ? mainTexture.name : null,
                hasMainTexture = mainTexture != null,
                hasColorProperty = material.HasProperty("_Color") || material.HasProperty("_BaseColor")
            };
        }

        private static ResourceUiHints BuildUiHints(
            UnityEngine.Object asset,
            string assetType,
            List<string> semanticTokens,
            ResourceTextureSummary textureSummary,
            ResourceMaterialSummary materialSummary,
            ResourcePrefabSummary prefabSummary)
        {
            string semanticBlob = string.Join(" ", semanticTokens);
            bool looksRepeatable = ContainsAny(semanticBlob, "slot", "cell", "card", "item", "tab", "button");
            bool looksFrame = ContainsAny(semanticBlob, "frame", "panel", "popup", "modal", "window");

            return new ResourceUiHints
            {
                isNineSliceCandidate = asset is Sprite sprite && (sprite.border.x + sprite.border.y + sprite.border.z + sprite.border.w) > 0f,
                isSingleImageRegion = asset is Sprite || asset is Texture2D,
                isRepeatableBlock = assetType.Equals("Prefab", StringComparison.OrdinalIgnoreCase) && looksRepeatable,
                isTextureBacked = textureSummary != null || (materialSummary != null && materialSummary.hasMainTexture),
                prefersPreserveAspect = (asset is Sprite || asset is Texture2D) && !looksFrame,
                hasTransparency = textureSummary != null && (textureSummary.alphaIsTransparency == true || textureSummary.hasAlpha == true),
                preferredUse = InferPreferredUse(semanticBlob, looksFrame, looksRepeatable),
                componentRoles = InferComponentRoles(prefabSummary)
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
            var componentCounts = new Dictionary<string, int>(StringComparer.Ordinal);
            var childPaths = new List<string>();
            var layoutGroupTypes = new HashSet<string>(StringComparer.Ordinal);
            var spritePaths = new HashSet<string>(StringComparer.Ordinal);
            var texturePaths = new HashSet<string>(StringComparer.Ordinal);
            var fontPaths = new HashSet<string>(StringComparer.Ordinal);
            var materialPaths = new HashSet<string>(StringComparer.Ordinal);

            CollectPrefabData(
                prefab.transform,
                prefab.name,
                componentTypes,
                componentCounts,
                childPaths,
                layoutGroupTypes,
                spritePaths,
                texturePaths,
                fontPaths,
                materialPaths);

            return new ResourcePrefabSummary
            {
                rootName = prefab.name,
                componentTypes = componentTypes.OrderBy(value => value).ToList(),
                componentCounts = componentCounts.OrderBy(pair => pair.Key).ToDictionary(pair => pair.Key, pair => pair.Value),
                childPaths = childPaths,
                layoutGroupTypes = layoutGroupTypes.OrderBy(value => value).ToList(),
                referencedSpritePaths = spritePaths.OrderBy(value => value).ToList(),
                referencedTexturePaths = texturePaths.OrderBy(value => value).ToList(),
                referencedFontPaths = fontPaths.OrderBy(value => value).ToList(),
                referencedMaterialPaths = materialPaths.OrderBy(value => value).ToList()
            };
        }

        private static void CollectPrefabData(
            Transform transform,
            string currentPath,
            HashSet<string> componentTypes,
            Dictionary<string, int> componentCounts,
            List<string> childPaths,
            HashSet<string> layoutGroupTypes,
            HashSet<string> spritePaths,
            HashSet<string> texturePaths,
            HashSet<string> fontPaths,
            HashSet<string> materialPaths)
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

                string componentTypeName = component.GetType().Name;
                componentTypes.Add(componentTypeName);
                if (componentCounts.ContainsKey(componentTypeName))
                {
                    componentCounts[componentTypeName] += 1;
                }
                else
                {
                    componentCounts[componentTypeName] = 1;
                }

                if (componentTypeName.EndsWith("LayoutGroup", StringComparison.Ordinal) ||
                    string.Equals(componentTypeName, "GridLayoutGroup", StringComparison.Ordinal) ||
                    string.Equals(componentTypeName, "ContentSizeFitter", StringComparison.Ordinal) ||
                    string.Equals(componentTypeName, "LayoutElement", StringComparison.Ordinal))
                {
                    layoutGroupTypes.Add(componentTypeName);
                }

                AddAssetPath(spritePaths, ReadObjectProperty(component, "sprite"));
                AddAssetPath(texturePaths, ReadObjectProperty(component, "texture"));
                AddAssetPath(texturePaths, ReadObjectProperty(component, "mainTexture"));
                AddAssetPath(fontPaths, ReadObjectProperty(component, "font"));
                AddAssetPath(materialPaths, ReadObjectProperty(component, "material"));
                AddAssetPath(materialPaths, ReadObjectProperty(component, "sharedMaterial"));
            }

            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                CollectPrefabData(
                    child,
                    currentPath + "/" + child.name,
                    componentTypes,
                    componentCounts,
                    childPaths,
                    layoutGroupTypes,
                    spritePaths,
                    texturePaths,
                    fontPaths,
                    materialPaths);
            }
        }

        private static List<string> BuildMetadataTokens(
            string assetType,
            ResourceAssetProvenance assetProvenance,
            ResourceTextureSummary textureSummary,
            ResourceMaterialSummary materialSummary,
            ResourcePrefabSummary prefabSummary)
        {
            var tokens = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            AddTokens(tokens, Tokenize(assetType));

            if (assetProvenance != null)
            {
                AddTokens(tokens, Tokenize(assetProvenance.mainAssetType));
                AddTokens(tokens, Tokenize(assetProvenance.importerType));
                AddTokens(tokens, Tokenize(assetProvenance.mainAssetName));
            }

            if (textureSummary != null)
            {
                AddTokens(tokens, Tokenize(textureSummary.sourceTextureName));
                AddTokens(tokens, Tokenize(textureSummary.textureImporterType));
                AddTokens(tokens, Tokenize(textureSummary.spriteImportMode));
                AddTokens(tokens, Tokenize(textureSummary.textureFormat));
                AddTokens(tokens, Tokenize(textureSummary.wrapMode));
                AddTokens(tokens, Tokenize(textureSummary.filterMode));

                if (textureSummary.hasAlpha == true)
                {
                    tokens.Add("has_alpha");
                }

                if (textureSummary.alphaIsTransparency == true)
                {
                    tokens.Add("alpha_transparency");
                }

                if (textureSummary.mipmapEnabled == false)
                {
                    tokens.Add("no_mipmap");
                }

                if (textureSummary.sRgbTexture == true)
                {
                    tokens.Add("srgb");
                }

                tokens.Add("texture_backed");
            }

            if (materialSummary != null)
            {
                AddTokens(tokens, Tokenize(materialSummary.shaderName));
                AddTokens(tokens, Tokenize(materialSummary.mainTextureName));
                if (materialSummary.hasMainTexture)
                {
                    tokens.Add("main_texture");
                }

                if (materialSummary.hasColorProperty)
                {
                    tokens.Add("tintable");
                }
            }

            if (prefabSummary != null)
            {
                AddTokens(tokens, prefabSummary.componentTypes.SelectMany(Tokenize));
                AddTokens(tokens, prefabSummary.layoutGroupTypes.SelectMany(Tokenize));
                AddTokens(tokens, prefabSummary.referencedSpritePaths.SelectMany(path => Tokenize(System.IO.Path.GetFileNameWithoutExtension(path))));
                AddTokens(tokens, prefabSummary.referencedTexturePaths.SelectMany(path => Tokenize(System.IO.Path.GetFileNameWithoutExtension(path))));
                AddTokens(tokens, prefabSummary.referencedFontPaths.SelectMany(path => Tokenize(System.IO.Path.GetFileNameWithoutExtension(path))));
                AddTokens(tokens, prefabSummary.referencedMaterialPaths.SelectMany(path => Tokenize(System.IO.Path.GetFileNameWithoutExtension(path))));
            }

            return tokens.OrderBy(value => value).ToList();
        }

        private static List<string> InferComponentRoles(ResourcePrefabSummary prefabSummary)
        {
            var roles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (prefabSummary == null)
            {
                return roles.ToList();
            }

            foreach (string componentType in prefabSummary.componentTypes)
            {
                if (string.Equals(componentType, "Button", StringComparison.Ordinal))
                {
                    roles.Add("button");
                }
                else if (string.Equals(componentType, "ScrollRect", StringComparison.Ordinal))
                {
                    roles.Add("scroll");
                    roles.Add("list");
                }
                else if (string.Equals(componentType, "Image", StringComparison.Ordinal) ||
                         string.Equals(componentType, "RawImage", StringComparison.Ordinal))
                {
                    roles.Add("image");
                }
                else if (string.Equals(componentType, "TextMeshProUGUI", StringComparison.Ordinal) ||
                         string.Equals(componentType, "TMP_Text", StringComparison.Ordinal))
                {
                    roles.Add("text");
                }
                else if (componentType.EndsWith("LayoutGroup", StringComparison.Ordinal) ||
                         string.Equals(componentType, "LayoutElement", StringComparison.Ordinal) ||
                         string.Equals(componentType, "ContentSizeFitter", StringComparison.Ordinal))
                {
                    roles.Add("layout");
                }
                else if (string.Equals(componentType, "Mask", StringComparison.Ordinal) ||
                         string.Equals(componentType, "RectMask2D", StringComparison.Ordinal))
                {
                    roles.Add("mask");
                }
            }

            return roles.OrderBy(value => value).ToList();
        }

        private static bool TextureFormatIncludesAlpha(TextureFormat format)
        {
            string name = format.ToString();
            return name.IndexOf("Alpha", StringComparison.OrdinalIgnoreCase) >= 0 ||
                   name.IndexOf("RGBA", StringComparison.OrdinalIgnoreCase) >= 0 ||
                   name.IndexOf("ARGB", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static UnityEngine.Object ReadObjectProperty(Component component, string propertyName)
        {
            if (component == null || string.IsNullOrWhiteSpace(propertyName))
            {
                return null;
            }

            string cacheKey = component.GetType().FullName + "|" + propertyName;
            if (!ComponentPropertyCache.TryGetValue(cacheKey, out PropertyInfo property))
            {
                property = component.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
                ComponentPropertyCache[cacheKey] = property;
            }

            if (property == null || !typeof(UnityEngine.Object).IsAssignableFrom(property.PropertyType))
            {
                return null;
            }

            return property.GetValue(component, null) as UnityEngine.Object;
        }

        private static void AddAssetPath(HashSet<string> target, UnityEngine.Object asset)
        {
            if (target == null || asset == null)
            {
                return;
            }

            string assetPath = AssetDatabase.GetAssetPath(asset);
            if (!string.IsNullOrWhiteSpace(assetPath))
            {
                target.Add(assetPath);
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
