using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor
{
    public static class UnityResourceRagArtifactActions
    {
        public static bool TryOpenPath(string path, out string error)
        {
            error = string.Empty;
            string normalizedPath = NormalizeExistingPath(path);
            if (string.IsNullOrWhiteSpace(normalizedPath))
            {
                error = "The selected artifact path does not exist yet.";
                return false;
            }

            try
            {
                Application.OpenURL(new Uri(normalizedPath).AbsoluteUri);
                return true;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                return false;
            }
        }

        public static bool TryRevealPath(string path, out string error)
        {
            error = string.Empty;
            string normalizedPath = NormalizeExistingPath(path);
            if (string.IsNullOrWhiteSpace(normalizedPath))
            {
                error = "The selected artifact path does not exist yet.";
                return false;
            }

            try
            {
                EditorUtility.RevealInFinder(normalizedPath);
                return true;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                return false;
            }
        }

        public static void CopyToClipboard(string value)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                EditorGUIUtility.systemCopyBuffer = value;
            }
        }

        public static bool TryPingProjectAsset(string path, out string error)
        {
            error = string.Empty;
            string assetPath = TryConvertToAssetPath(path);
            if (string.IsNullOrWhiteSpace(assetPath))
            {
                error = "This artifact is not a Unity project asset path.";
                return false;
            }

            UnityEngine.Object asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(assetPath);
            if (asset == null)
            {
                error = $"Unity could not load the asset at `{assetPath}`.";
                return false;
            }

            Selection.activeObject = asset;
            EditorGUIUtility.PingObject(asset);
            return true;
        }

        public static bool TrySelectHierarchyObject(string objectName, out string error)
        {
            error = string.Empty;
            if (string.IsNullOrWhiteSpace(objectName))
            {
                error = "No hierarchy object name is available yet.";
                return false;
            }

            foreach (GameObject candidate in Resources.FindObjectsOfTypeAll<GameObject>())
            {
                if (!candidate.scene.IsValid())
                {
                    continue;
                }

                if (!string.Equals(candidate.name, objectName, StringComparison.Ordinal))
                {
                    continue;
                }

                Selection.activeObject = candidate;
                EditorGUIUtility.PingObject(candidate);
                return true;
            }

            error = $"No loaded hierarchy object named `{objectName}` was found.";
            return false;
        }

        private static string NormalizeExistingPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return string.Empty;
            }

            try
            {
                string normalized = path.Trim();
                if (!Path.IsPathRooted(normalized))
                {
                    string assetPath = TryConvertToAssetPath(normalized);
                    if (!string.IsNullOrWhiteSpace(assetPath))
                    {
                        normalized = Path.GetFullPath(Path.Combine(ProjectRootPath, assetPath));
                    }
                    else
                    {
                        normalized = Path.GetFullPath(Path.Combine(ProjectRootPath, normalized));
                    }
                }

                return File.Exists(normalized) || Directory.Exists(normalized) ? normalized : string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private static string TryConvertToAssetPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return string.Empty;
            }

            string trimmed = path.Trim().Replace('\\', '/');
            if (trimmed.StartsWith("Assets/", StringComparison.Ordinal))
            {
                return trimmed;
            }

            try
            {
                string absolute = Path.GetFullPath(trimmed).Replace('\\', '/');
                string projectRoot = ProjectRootPath.Replace('\\', '/').TrimEnd('/');
                if (!absolute.StartsWith(projectRoot + "/", StringComparison.Ordinal))
                {
                    return string.Empty;
                }

                string relative = absolute.Substring(projectRoot.Length + 1);
                return relative.StartsWith("Assets/", StringComparison.Ordinal) ? relative : string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private static string ProjectRootPath => Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
    }
}
