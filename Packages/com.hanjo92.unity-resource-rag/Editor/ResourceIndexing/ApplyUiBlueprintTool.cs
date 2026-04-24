using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Applies a structured UI blueprint using real Unity assets instead of ad-hoc placeholder shapes.
    /// </summary>
    [McpForUnityTool(
        "apply_ui_blueprint",
        Description = "Validate or apply a structured UI blueprint. Supports canvas, container, prefab_instance, image, and tmp_text nodes plus layout groups, layout elements, and project-specific custom components."
    )]
    public static class ApplyUiBlueprintTool
    {
        private static readonly HashSet<string> SupportedNodeKinds = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "canvas",
            "container",
            "prefab_instance",
            "image",
            "tmp_text"
        };
        private static readonly Dictionary<string, Type> TypeCache = new Dictionary<string, Type>(StringComparer.Ordinal);
        private static readonly Dictionary<string, PropertyInfo> PropertyCache = new Dictionary<string, PropertyInfo>(StringComparer.Ordinal);
        private static readonly Dictionary<string, FieldInfo> FieldCache = new Dictionary<string, FieldInfo>(StringComparer.Ordinal);

        public sealed class Parameters
        {
            [ToolParameter("Action to perform: validate or apply.", Required = false, DefaultValue = "validate")]
            public string action { get; set; } = "validate";

            [ToolParameter("Inline blueprint JSON string.", Required = false)]
            public string blueprintJson { get; set; }

            [ToolParameter("Project-relative or absolute path to a blueprint JSON file.", Required = false)]
            public string blueprintPath { get; set; }
        }

        public static object HandleCommand(JObject @params)
        {
            try
            {
                Parameters parameters = @params == null
                    ? new Parameters()
                    : @params.ToObject<Parameters>() ?? new Parameters();

                if (!TryLoadBlueprint(@params, parameters, out UiBlueprintDocument blueprint, out string error))
                {
                    return new ErrorResponse(error);
                }

                List<UiBlueprintIssue> issues = ValidateBlueprint(blueprint);
                bool hasErrors = issues.Any(issue => string.Equals(issue.severity, "error", StringComparison.OrdinalIgnoreCase));

                if (string.Equals(parameters.action, "validate", StringComparison.OrdinalIgnoreCase))
                {
                    return new SuccessResponse(
                        hasErrors ? "Blueprint validation found errors." : "Blueprint validation succeeded.",
                        new
                        {
                            screenName = blueprint.screenName,
                            hasErrors,
                            issues,
                            verificationHint = BuildVerificationHint(blueprint)
                        });
                }

                if (!string.Equals(parameters.action, "apply", StringComparison.OrdinalIgnoreCase))
                {
                    return new ErrorResponse("Unsupported action. Expected 'validate' or 'apply'.");
                }

                if (hasErrors)
                {
                    return new ErrorResponse("Blueprint validation failed.", new { issues });
                }

                List<UiBlueprintApplyResult> results = new List<UiBlueprintApplyResult>();
                GameObject root = ApplyNodeRecursive(blueprint.root, null, results);

                Selection.activeGameObject = root;
                return new SuccessResponse(
                    "Applied UI blueprint successfully.",
                    new
                    {
                        screenName = blueprint.screenName,
                        rootInstanceId = root.GetInstanceID(),
                        rootName = root.name,
                        created = results,
                        verificationHint = BuildVerificationHint(blueprint, root.name)
                    });
            }
            catch (Exception ex)
            {
                return new ErrorResponse("Failed to apply UI blueprint: " + ex.Message);
            }
        }

        private static bool TryLoadBlueprint(
            JObject rawParams,
            Parameters parameters,
            out UiBlueprintDocument blueprint,
            out string error)
        {
            blueprint = null;
            error = null;

            JToken inlineBlueprint = rawParams?["blueprint"];
            if (inlineBlueprint != null && inlineBlueprint.Type == JTokenType.Object)
            {
                blueprint = inlineBlueprint.ToObject<UiBlueprintDocument>();
                if (blueprint == null)
                {
                    error = "Could not deserialize inline blueprint object.";
                    return false;
                }

                return true;
            }

            if (!string.IsNullOrWhiteSpace(parameters.blueprintJson))
            {
                blueprint = JsonConvert.DeserializeObject<UiBlueprintDocument>(parameters.blueprintJson);
                if (blueprint == null)
                {
                    error = "Could not deserialize blueprintJson.";
                    return false;
                }

                return true;
            }

            if (!string.IsNullOrWhiteSpace(parameters.blueprintPath))
            {
                string resolvedPath = ResolveBlueprintPath(parameters.blueprintPath);
                if (!File.Exists(resolvedPath))
                {
                    error = $"Blueprint file not found: {resolvedPath}";
                    return false;
                }

                blueprint = JsonConvert.DeserializeObject<UiBlueprintDocument>(File.ReadAllText(resolvedPath));
                if (blueprint == null)
                {
                    error = $"Could not deserialize blueprint file: {resolvedPath}";
                    return false;
                }

                return true;
            }

            error = "No blueprint provided. Use 'blueprint', 'blueprintJson', or 'blueprintPath'.";
            return false;
        }

        private static string ResolveBlueprintPath(string blueprintPath)
        {
            string trimmedPath = blueprintPath?.Trim();
            if (string.IsNullOrWhiteSpace(trimmedPath))
            {
                return string.Empty;
            }

            if (Path.IsPathRooted(trimmedPath))
            {
                return Path.GetFullPath(trimmedPath).Replace('\\', '/');
            }

            string normalizedPath = trimmedPath.Replace('\\', '/');
            if (normalizedPath.Equals("Samples~", StringComparison.OrdinalIgnoreCase) ||
                normalizedPath.StartsWith("Samples~/", StringComparison.OrdinalIgnoreCase))
            {
                UnityEditor.PackageManager.PackageInfo packageInfo =
                    UnityEditor.PackageManager.PackageInfo.FindForAssembly(Assembly.GetExecutingAssembly());
                if (packageInfo != null && !string.IsNullOrWhiteSpace(packageInfo.resolvedPath))
                {
                    string relativeSamplePath = normalizedPath.Equals("Samples~", StringComparison.OrdinalIgnoreCase)
                        ? string.Empty
                        : normalizedPath.Substring("Samples~/".Length);
                    return Path.GetFullPath(Path.Combine(packageInfo.resolvedPath, "Samples~", relativeSamplePath)).Replace('\\', '/');
                }
            }

            return ResourceCatalogStorage.ResolveProjectPath(trimmedPath, trimmedPath);
        }

        private static List<UiBlueprintIssue> ValidateBlueprint(UiBlueprintDocument blueprint)
        {
            var issues = new List<UiBlueprintIssue>();
            if (blueprint == null)
            {
                issues.Add(new UiBlueprintIssue
                {
                    severity = "error",
                    message = "Blueprint document is null."
                });
                return issues;
            }

            if (blueprint.root == null)
            {
                issues.Add(new UiBlueprintIssue
                {
                    severity = "error",
                    message = "Blueprint root node is missing."
                });
                return issues;
            }

            ValidateNode(blueprint.root, issues);
            return issues;
        }

        private static void ValidateNode(UiBlueprintNode node, List<UiBlueprintIssue> issues)
        {
            if (node == null)
            {
                issues.Add(new UiBlueprintIssue
                {
                    severity = "error",
                    message = "Encountered a null node in the blueprint tree."
                });
                return;
            }

            if (string.IsNullOrWhiteSpace(node.name))
            {
                issues.Add(BuildIssue("error", node, "Node name is required."));
            }

            if (string.IsNullOrWhiteSpace(node.kind) || !SupportedNodeKinds.Contains(node.kind))
            {
                issues.Add(BuildIssue("error", node, "Unsupported node kind. Expected canvas, container, prefab_instance, image, or tmp_text."));
            }

            if (string.Equals(node.kind, "prefab_instance", StringComparison.OrdinalIgnoreCase))
            {
                if (node.asset == null)
                {
                    issues.Add(BuildIssue("error", node, "prefab_instance nodes require an asset reference."));
                }
                else if (!UnityAssetResolver.TryResolvePrefab(node.asset, out _, out _, out string error))
                {
                    issues.Add(BuildIssue("error", node, error));
                }
            }

            if (string.Equals(node.kind, "image", StringComparison.OrdinalIgnoreCase))
            {
                if (node.asset == null)
                {
                    issues.Add(BuildIssue("error", node, "image nodes require an asset reference."));
                }
                else if (!UnityAssetResolver.TryResolveSprite(node.asset, out _, out _, out string error))
                {
                    issues.Add(BuildIssue("error", node, error));
                }
            }

            if (string.Equals(node.kind, "tmp_text", StringComparison.OrdinalIgnoreCase))
            {
                if (node.text == null)
                {
                    issues.Add(BuildIssue("error", node, "tmp_text nodes require a text spec."));
                }
                else if (node.text.fontAsset != null &&
                         !UnityAssetResolver.TryResolveTmpFont(node.text.fontAsset, out _, out _, out string error))
                {
                    issues.Add(BuildIssue("error", node, error));
                }
            }

            ValidateLayoutGroup(node, issues);
            ValidateCustomComponents(node, issues);

            if (node.children == null)
            {
                return;
            }

            foreach (UiBlueprintNode child in node.children)
            {
                ValidateNode(child, issues);
            }
        }

        private static UiBlueprintIssue BuildIssue(string severity, UiBlueprintNode node, string message)
        {
            return new UiBlueprintIssue
            {
                severity = severity,
                nodeId = node?.id,
                nodeName = node?.name,
                message = message
            };
        }

        private static GameObject ApplyNodeRecursive(
            UiBlueprintNode node,
            Transform parent,
            List<UiBlueprintApplyResult> results)
        {
            GameObject instance = CreateNode(node);
            if (parent != null)
            {
                instance.transform.SetParent(parent, false);
            }

            instance.name = node.name;
            instance.SetActive(node.active);

            RectTransform rectTransform = instance.GetComponent<RectTransform>();
            if (rectTransform == null)
            {
                rectTransform = instance.AddComponent<RectTransform>();
            }

            ApplyRectTransform(rectTransform, node.rect);

            if (string.Equals(node.kind, "canvas", StringComparison.OrdinalIgnoreCase))
            {
                ConfigureCanvas(instance, node.canvasScaler);
            }
            else if (string.Equals(node.kind, "image", StringComparison.OrdinalIgnoreCase))
            {
                ConfigureImage(instance, node.asset, node.image);
            }
            else if (string.Equals(node.kind, "tmp_text", StringComparison.OrdinalIgnoreCase))
            {
                ConfigureTmpText(instance, node.text);
            }

            ApplyLayoutGroup(instance, node.layoutGroup);
            ApplyLayoutElement(instance, node.layoutElement);
            ApplyCustomComponents(instance, node.components);

            string assetPath = node.asset?.path;
            if (string.IsNullOrWhiteSpace(assetPath) && node.asset != null && !string.IsNullOrWhiteSpace(node.asset.guid))
            {
                assetPath = AssetDatabase.GUIDToAssetPath(node.asset.guid);
            }
            if (string.IsNullOrWhiteSpace(assetPath) &&
                node.text != null &&
                node.text.fontAsset != null &&
                !string.IsNullOrWhiteSpace(node.text.fontAsset.guid))
            {
                assetPath = AssetDatabase.GUIDToAssetPath(node.text.fontAsset.guid);
            }

            results.Add(new UiBlueprintApplyResult
            {
                nodeId = node.id,
                nodeName = node.name,
                kind = node.kind,
                hierarchyPath = BuildHierarchyPath(instance.transform),
                instanceId = instance.GetInstanceID(),
                assetPath = assetPath
            });

            if (node.children != null)
            {
                foreach (UiBlueprintNode child in node.children)
                {
                    ApplyNodeRecursive(child, instance.transform, results);
                }
            }

            return instance;
        }

        private static GameObject CreateNode(UiBlueprintNode node)
        {
            if (string.Equals(node.kind, "prefab_instance", StringComparison.OrdinalIgnoreCase))
            {
                if (!UnityAssetResolver.TryResolvePrefab(node.asset, out GameObject prefab, out _, out string error))
                {
                    throw new InvalidOperationException(error);
                }

                GameObject instantiated = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
                if (instantiated == null)
                {
                    throw new InvalidOperationException("Failed to instantiate prefab for blueprint node '" + node.name + "'.");
                }

                return instantiated;
            }

            GameObject gameObject = new GameObject(node.name ?? "UiNode", typeof(RectTransform));
            if (string.Equals(node.kind, "canvas", StringComparison.OrdinalIgnoreCase))
            {
                gameObject.AddComponent<Canvas>();
            }

            return gameObject;
        }

        private static void ConfigureCanvas(GameObject gameObject, UiCanvasScalerSpec spec)
        {
            Canvas canvas = gameObject.GetComponent<Canvas>();
            if (canvas == null)
            {
                canvas = gameObject.AddComponent<Canvas>();
            }

            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            EnsureComponent(gameObject, "UnityEngine.UI.GraphicRaycaster");

            Component canvasScaler = EnsureComponent(gameObject, "UnityEngine.UI.CanvasScaler");
            if (canvasScaler == null || spec == null)
            {
                return;
            }

            SetEnumProperty(canvasScaler, "uiScaleMode", spec.uiScaleMode);
            if (spec.referenceResolution != null)
            {
                SetProperty(canvasScaler, "referenceResolution", new Vector2(spec.referenceResolution.x, spec.referenceResolution.y));
            }

            SetEnumProperty(canvasScaler, "screenMatchMode", spec.screenMatchMode);
            if (spec.matchWidthOrHeight.HasValue)
            {
                SetProperty(canvasScaler, "matchWidthOrHeight", spec.matchWidthOrHeight.Value);
            }
        }

        private static void ConfigureTmpText(GameObject gameObject, UiTmpTextSpec spec)
        {
            if (spec == null)
            {
                throw new InvalidOperationException("tmp_text node is missing its text spec.");
            }

            Type textType = ResolveType("TMPro.TextMeshProUGUI");
            if (textType == null)
            {
                throw new InvalidOperationException("TMPro.TextMeshProUGUI could not be resolved. Ensure TextMeshPro is installed.");
            }

            Component textComponent = EnsureComponent(gameObject, "TMPro.TextMeshProUGUI");
            if (textComponent == null)
            {
                throw new InvalidOperationException("Failed to create TextMeshProUGUI component.");
            }

            SetProperty(textComponent, "text", spec.value ?? string.Empty);

            if (spec.fontSize.HasValue)
            {
                SetProperty(textComponent, "fontSize", spec.fontSize.Value);
            }

            if (spec.enableAutoSizing.HasValue)
            {
                SetProperty(textComponent, "enableAutoSizing", spec.enableAutoSizing.Value);
            }

            if (spec.raycastTarget.HasValue)
            {
                SetProperty(textComponent, "raycastTarget", spec.raycastTarget.Value);
            }

            if (!string.IsNullOrWhiteSpace(spec.alignment))
            {
                SetEnumProperty(textComponent, "alignment", spec.alignment);
            }

            if (!string.IsNullOrWhiteSpace(spec.color) && TryParseColor(spec.color, out Color color))
            {
                SetProperty(textComponent, "color", color);
            }

            string error = null;
            if (spec.fontAsset != null &&
                UnityAssetResolver.TryResolveTmpFont(spec.fontAsset, out UnityEngine.Object fontAsset, out _, out error))
            {
                SetProperty(textComponent, "font", fontAsset);
            }
            else if (spec.fontAsset != null)
            {
                throw new InvalidOperationException(error);
            }
        }

        private static void ConfigureImage(GameObject gameObject, UiAssetReference assetReference, UiImageSpec imageSpec)
        {
            if (!UnityAssetResolver.TryResolveSprite(assetReference, out Sprite sprite, out _, out string error))
            {
                throw new InvalidOperationException(error);
            }

            Component image = EnsureComponent(gameObject, "UnityEngine.UI.Image");
            if (image == null)
            {
                throw new InvalidOperationException("UnityEngine.UI.Image could not be resolved. Ensure com.unity.ugui is installed.");
            }

            SetProperty(image, "sprite", sprite);

            if (imageSpec != null)
            {
                SetEnumProperty(image, "type", imageSpec.type);
                if (imageSpec.preserveAspect.HasValue)
                {
                    SetProperty(image, "preserveAspect", imageSpec.preserveAspect.Value);
                }

                if (imageSpec.raycastTarget.HasValue)
                {
                    SetProperty(image, "raycastTarget", imageSpec.raycastTarget.Value);
                }

                if (!string.IsNullOrWhiteSpace(imageSpec.color) && TryParseColor(imageSpec.color, out Color color))
                {
                    SetProperty(image, "color", color);
                }
            }
        }

        private static void ApplyLayoutGroup(GameObject gameObject, UiLayoutGroupSpec spec)
        {
            if (gameObject == null || spec == null || string.IsNullOrWhiteSpace(spec.kind))
            {
                return;
            }

            string normalizedKind = spec.kind.Trim().ToLowerInvariant();
            string typeName = normalizedKind switch
            {
                "horizontal" => "UnityEngine.UI.HorizontalLayoutGroup",
                "vertical" => "UnityEngine.UI.VerticalLayoutGroup",
                "grid" => "UnityEngine.UI.GridLayoutGroup",
                _ => null
            };

            if (typeName == null)
            {
                return;
            }

            Component layoutGroup = EnsureComponent(gameObject, typeName);
            if (layoutGroup == null)
            {
                return;
            }

            if (spec.padding != null)
            {
                SetProperty(layoutGroup, "padding", new RectOffset(
                    spec.padding.left,
                    spec.padding.right,
                    spec.padding.top,
                    spec.padding.bottom));
            }

            if (!string.IsNullOrWhiteSpace(spec.childAlignment))
            {
                SetEnumProperty(layoutGroup, "childAlignment", spec.childAlignment);
            }

            if (spec.spacing.HasValue)
            {
                SetProperty(layoutGroup, "spacing", spec.spacing.Value);
            }

            if (spec.childControlWidth.HasValue)
            {
                SetProperty(layoutGroup, "childControlWidth", spec.childControlWidth.Value);
            }

            if (spec.childControlHeight.HasValue)
            {
                SetProperty(layoutGroup, "childControlHeight", spec.childControlHeight.Value);
            }

            if (spec.childForceExpandWidth.HasValue)
            {
                SetProperty(layoutGroup, "childForceExpandWidth", spec.childForceExpandWidth.Value);
            }

            if (spec.childForceExpandHeight.HasValue)
            {
                SetProperty(layoutGroup, "childForceExpandHeight", spec.childForceExpandHeight.Value);
            }

            if (spec.childScaleWidth.HasValue)
            {
                SetProperty(layoutGroup, "childScaleWidth", spec.childScaleWidth.Value);
            }

            if (spec.childScaleHeight.HasValue)
            {
                SetProperty(layoutGroup, "childScaleHeight", spec.childScaleHeight.Value);
            }

            if (normalizedKind == "grid")
            {
                if (spec.spacing2 != null)
                {
                    SetProperty(layoutGroup, "spacing", new Vector2(spec.spacing2.x, spec.spacing2.y));
                }

                if (spec.cellSize != null)
                {
                    SetProperty(layoutGroup, "cellSize", new Vector2(spec.cellSize.x, spec.cellSize.y));
                }

                if (!string.IsNullOrWhiteSpace(spec.constraint))
                {
                    SetEnumProperty(layoutGroup, "constraint", spec.constraint);
                }

                if (spec.constraintCount.HasValue)
                {
                    SetProperty(layoutGroup, "constraintCount", spec.constraintCount.Value);
                }

                if (!string.IsNullOrWhiteSpace(spec.startCorner))
                {
                    SetEnumProperty(layoutGroup, "startCorner", spec.startCorner);
                }

                if (!string.IsNullOrWhiteSpace(spec.startAxis))
                {
                    SetEnumProperty(layoutGroup, "startAxis", spec.startAxis);
                }
            }
        }

        private static void ApplyLayoutElement(GameObject gameObject, UiLayoutElementSpec spec)
        {
            if (gameObject == null || spec == null)
            {
                return;
            }

            Component layoutElement = EnsureComponent(gameObject, "UnityEngine.UI.LayoutElement");
            if (layoutElement == null)
            {
                return;
            }

            if (spec.minWidth.HasValue)
            {
                SetProperty(layoutElement, "minWidth", spec.minWidth.Value);
            }

            if (spec.minHeight.HasValue)
            {
                SetProperty(layoutElement, "minHeight", spec.minHeight.Value);
            }

            if (spec.preferredWidth.HasValue)
            {
                SetProperty(layoutElement, "preferredWidth", spec.preferredWidth.Value);
            }

            if (spec.preferredHeight.HasValue)
            {
                SetProperty(layoutElement, "preferredHeight", spec.preferredHeight.Value);
            }

            if (spec.flexibleWidth.HasValue)
            {
                SetProperty(layoutElement, "flexibleWidth", spec.flexibleWidth.Value);
            }

            if (spec.flexibleHeight.HasValue)
            {
                SetProperty(layoutElement, "flexibleHeight", spec.flexibleHeight.Value);
            }

            if (spec.ignoreLayout.HasValue)
            {
                SetProperty(layoutElement, "ignoreLayout", spec.ignoreLayout.Value);
            }
        }

        private static void ApplyCustomComponents(GameObject gameObject, List<UiCustomComponentSpec> components)
        {
            if (gameObject == null || components == null)
            {
                return;
            }

            foreach (UiCustomComponentSpec componentSpec in components)
            {
                if (componentSpec == null || string.IsNullOrWhiteSpace(componentSpec.typeName))
                {
                    continue;
                }

                Type type = ResolveType(componentSpec.typeName);
                if (type == null)
                {
                    throw new InvalidOperationException("Could not resolve custom component type '" + componentSpec.typeName + "'.");
                }

                Component component = gameObject.GetComponent(type) ?? gameObject.AddComponent(type);
                ApplyObjectProperties(component, componentSpec.properties);
            }
        }

        private static void ApplyRectTransform(RectTransform rectTransform, UiRectTransformSpec rect)
        {
            if (rectTransform == null || rect == null)
            {
                return;
            }

            if (rect.anchorMin != null)
            {
                rectTransform.anchorMin = new Vector2(rect.anchorMin.x, rect.anchorMin.y);
            }

            if (rect.anchorMax != null)
            {
                rectTransform.anchorMax = new Vector2(rect.anchorMax.x, rect.anchorMax.y);
            }

            if (rect.pivot != null)
            {
                rectTransform.pivot = new Vector2(rect.pivot.x, rect.pivot.y);
            }

            if (rect.anchoredPosition != null)
            {
                rectTransform.anchoredPosition = new Vector2(rect.anchoredPosition.x, rect.anchoredPosition.y);
            }

            if (rect.sizeDelta != null)
            {
                rectTransform.sizeDelta = new Vector2(rect.sizeDelta.x, rect.sizeDelta.y);
            }

            if (rect.offsetMin != null)
            {
                rectTransform.offsetMin = new Vector2(rect.offsetMin.x, rect.offsetMin.y);
            }

            if (rect.offsetMax != null)
            {
                rectTransform.offsetMax = new Vector2(rect.offsetMax.x, rect.offsetMax.y);
            }
        }

        private static Component EnsureComponent(GameObject gameObject, string typeName)
        {
            Type type = ResolveType(typeName);
            if (type == null)
            {
                return null;
            }

            Component existing = gameObject.GetComponent(type);
            return existing != null ? existing : gameObject.AddComponent(type);
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

            Assembly[] assemblies = AppDomain.CurrentDomain.GetAssemblies();
            for (int i = 0; i < assemblies.Length; i++)
            {
                resolved = assemblies[i].GetType(typeName);
                if (resolved != null)
                {
                    TypeCache[typeName] = resolved;
                    return resolved;
                }
            }

            TypeCache[typeName] = null;
            return null;
        }

        private static void SetProperty(object target, string propertyName, object value)
        {
            if (target == null)
            {
                return;
            }

            PropertyInfo property = GetCachedProperty(target.GetType(), propertyName, BindingFlags.Public | BindingFlags.Instance);
            if (property != null && property.CanWrite)
            {
                property.SetValue(target, value);
            }
        }

        private static void ApplyObjectProperties(object target, JObject properties)
        {
            if (target == null || properties == null)
            {
                return;
            }

            foreach (JProperty property in properties.Properties())
            {
                SetPropertyOrField(target, property.Name, property.Value);
            }
        }

        private static void SetPropertyOrField(object target, string propertyName, JToken token)
        {
            if (target == null)
            {
                return;
            }

            Type type = target.GetType();
            PropertyInfo property = GetCachedProperty(type, propertyName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (property != null && property.CanWrite && TryConvertToken(token, property.PropertyType, out object propertyValue))
            {
                property.SetValue(target, propertyValue);
                return;
            }

            FieldInfo field = GetCachedField(type, propertyName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (field != null && TryConvertToken(token, field.FieldType, out object fieldValue))
            {
                field.SetValue(target, fieldValue);
            }
        }

        private static void SetEnumProperty(object target, string propertyName, string enumValue)
        {
            if (target == null || string.IsNullOrWhiteSpace(enumValue))
            {
                return;
            }

            PropertyInfo property = GetCachedProperty(target.GetType(), propertyName, BindingFlags.Public | BindingFlags.Instance);
            if (property == null || !property.CanWrite || !property.PropertyType.IsEnum)
            {
                return;
            }

            try
            {
                object parsed = Enum.Parse(property.PropertyType, enumValue, true);
                property.SetValue(target, parsed);
            }
            catch
            {
                // Ignore invalid enum values so blueprint validation can evolve independently.
            }
        }

        private static PropertyInfo GetCachedProperty(Type type, string propertyName, BindingFlags flags)
        {
            if (type == null || string.IsNullOrWhiteSpace(propertyName))
            {
                return null;
            }

            string cacheKey = string.Concat(type.AssemblyQualifiedName, "|", propertyName, "|", ((int)flags).ToString());
            if (PropertyCache.TryGetValue(cacheKey, out PropertyInfo cachedProperty))
            {
                return cachedProperty;
            }

            PropertyInfo property = type.GetProperty(propertyName, flags);
            PropertyCache[cacheKey] = property;
            return property;
        }

        private static FieldInfo GetCachedField(Type type, string fieldName, BindingFlags flags)
        {
            if (type == null || string.IsNullOrWhiteSpace(fieldName))
            {
                return null;
            }

            string cacheKey = string.Concat(type.AssemblyQualifiedName, "|", fieldName, "|", ((int)flags).ToString());
            if (FieldCache.TryGetValue(cacheKey, out FieldInfo cachedField))
            {
                return cachedField;
            }

            FieldInfo field = type.GetField(fieldName, flags);
            FieldCache[cacheKey] = field;
            return field;
        }

        private static string BuildHierarchyPath(Transform transform)
        {
            string path = transform.name;
            while (transform.parent != null)
            {
                transform = transform.parent;
                path = transform.name + "/" + path;
            }

            return path;
        }

        private static bool TryParseColor(string input, out Color color)
        {
            color = Color.white;
            if (string.IsNullOrWhiteSpace(input))
            {
                return false;
            }

            return ColorUtility.TryParseHtmlString(input, out color);
        }

        private static bool TryConvertToken(JToken token, Type targetType, out object value)
        {
            value = null;
            if (token == null)
            {
                return false;
            }

            Type effectiveType = Nullable.GetUnderlyingType(targetType) ?? targetType;

            if (effectiveType == typeof(string))
            {
                value = token.Type == JTokenType.Null ? null : token.ToString();
                return true;
            }

            if (effectiveType == typeof(int))
            {
                value = token.ToObject<int>();
                return true;
            }

            if (effectiveType == typeof(float))
            {
                value = token.ToObject<float>();
                return true;
            }

            if (effectiveType == typeof(bool))
            {
                value = token.ToObject<bool>();
                return true;
            }

            if (effectiveType.IsEnum)
            {
                value = Enum.Parse(effectiveType, token.ToString(), true);
                return true;
            }

            if (effectiveType == typeof(Vector2))
            {
                if (TryConvertVector2(token, out Vector2 vector2))
                {
                    value = vector2;
                    return true;
                }

                return false;
            }

            if (effectiveType == typeof(Vector3))
            {
                if (TryConvertVector3(token, out Vector3 vector3))
                {
                    value = vector3;
                    return true;
                }

                return false;
            }

            if (effectiveType == typeof(Color))
            {
                if (token.Type == JTokenType.String && TryParseColor(token.ToString(), out Color color))
                {
                    value = color;
                    return true;
                }

                return false;
            }

            if (effectiveType == typeof(RectOffset))
            {
                if (token.Type == JTokenType.Object)
                {
                    value = new RectOffset(
                        token["left"]?.ToObject<int>() ?? 0,
                        token["right"]?.ToObject<int>() ?? 0,
                        token["top"]?.ToObject<int>() ?? 0,
                        token["bottom"]?.ToObject<int>() ?? 0);
                    return true;
                }

                return false;
            }

            if (typeof(UnityEngine.Object).IsAssignableFrom(effectiveType) && token.Type == JTokenType.Object)
            {
                UiAssetReference reference = token.ToObject<UiAssetReference>();
                if (reference != null && UnityAssetResolver.TryResolve(reference, out UnityEngine.Object asset, out _, out _))
                {
                    value = asset;
                    return true;
                }
            }

            try
            {
                value = token.ToObject(effectiveType);
                return value != null;
            }
            catch
            {
                return false;
            }
        }

        private static bool TryConvertVector2(JToken token, out Vector2 vector)
        {
            vector = Vector2.zero;
            if (token.Type == JTokenType.Object)
            {
                vector = new Vector2(
                    token["x"]?.ToObject<float>() ?? 0f,
                    token["y"]?.ToObject<float>() ?? 0f);
                return true;
            }

            if (token.Type == JTokenType.Array && token.Count() >= 2)
            {
                vector = new Vector2(token[0].ToObject<float>(), token[1].ToObject<float>());
                return true;
            }

            return false;
        }

        private static bool TryConvertVector3(JToken token, out Vector3 vector)
        {
            vector = Vector3.zero;
            if (token.Type == JTokenType.Object)
            {
                vector = new Vector3(
                    token["x"]?.ToObject<float>() ?? 0f,
                    token["y"]?.ToObject<float>() ?? 0f,
                    token["z"]?.ToObject<float>() ?? 0f);
                return true;
            }

            if (token.Type == JTokenType.Array && token.Count() >= 3)
            {
                vector = new Vector3(token[0].ToObject<float>(), token[1].ToObject<float>(), token[2].ToObject<float>());
                return true;
            }

            return false;
        }

        private static void ValidateLayoutGroup(UiBlueprintNode node, List<UiBlueprintIssue> issues)
        {
            if (node == null || node.layoutGroup == null || string.IsNullOrWhiteSpace(node.layoutGroup.kind))
            {
                return;
            }

            string kind = node.layoutGroup.kind.Trim().ToLowerInvariant();
            if (kind != "horizontal" && kind != "vertical" && kind != "grid")
            {
                issues.Add(BuildIssue("error", node, "Unsupported layoutGroup.kind. Expected Horizontal, Vertical, or Grid."));
            }
        }

        private static void ValidateCustomComponents(UiBlueprintNode node, List<UiBlueprintIssue> issues)
        {
            if (node == null || node.components == null)
            {
                return;
            }

            foreach (UiCustomComponentSpec component in node.components)
            {
                if (component == null || string.IsNullOrWhiteSpace(component.typeName))
                {
                    issues.Add(BuildIssue("error", node, "Custom components must include a typeName."));
                    continue;
                }

                if (ResolveType(component.typeName) == null)
                {
                    issues.Add(BuildIssue("error", node, "Could not resolve custom component type '" + component.typeName + "'."));
                }
            }
        }

        private static UiBlueprintVerificationHint BuildVerificationHint(UiBlueprintDocument blueprint, string rootName = null)
        {
            string targetName = !string.IsNullOrWhiteSpace(rootName)
                ? rootName
                : blueprint?.root?.name;

            return new UiBlueprintVerificationHint
            {
                tool = "manage_camera",
                parameters = new
                {
                    action = "screenshot",
                    capture_source = "scene_view",
                    view_target = targetName,
                    include_image = true,
                    max_resolution = 768
                }
            };
        }
    }
}
