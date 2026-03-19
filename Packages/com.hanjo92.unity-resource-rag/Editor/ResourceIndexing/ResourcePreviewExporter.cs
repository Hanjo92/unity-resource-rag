using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Exports readable PNG previews that the sidecar vector pipeline can embed later.
    /// </summary>
    public static class ResourcePreviewExporter
    {
        public static bool TryExportPreview(
            UnityEngine.Object asset,
            string guid,
            long localFileId,
            string previewDirectory,
            out ResourcePreviewInfo previewInfo)
        {
            previewInfo = null;
            if (asset == null)
            {
                return false;
            }

            Texture2D readableTexture = null;
            try
            {
                readableTexture = BuildReadablePreview(asset);
                if (readableTexture == null)
                {
                    return false;
                }

                Directory.CreateDirectory(previewDirectory);
                string fileName = string.Format("{0}_{1}.png", SanitizeFileName(guid), localFileId);
                string outputPath = Path.Combine(previewDirectory, fileName).Replace('\\', '/');
                File.WriteAllBytes(outputPath, readableTexture.EncodeToPNG());

                previewInfo = new ResourcePreviewInfo
                {
                    path = outputPath,
                    width = readableTexture.width,
                    height = readableTexture.height
                };

                return true;
            }
            catch
            {
                return false;
            }
            finally
            {
                if (readableTexture != null)
                {
                    UnityEngine.Object.DestroyImmediate(readableTexture);
                }
            }
        }

        private static Texture2D BuildReadablePreview(UnityEngine.Object asset)
        {
            if (asset is Sprite sprite)
            {
                return ExtractSpriteTexture(sprite);
            }

            if (asset is Texture2D texture)
            {
                return CopyTexture(texture);
            }

            Texture2D previewTexture = AssetPreview.GetAssetPreview(asset);
            if (previewTexture == null)
            {
                previewTexture = AssetPreview.GetMiniThumbnail(asset);
            }

            return previewTexture == null ? null : CopyTexture(previewTexture);
        }

        private static Texture2D ExtractSpriteTexture(Sprite sprite)
        {
            Texture2D source = sprite.texture;
            if (source == null)
            {
                return null;
            }

            Texture2D readableSource = CopyTexture(source);
            if (readableSource == null)
            {
                return null;
            }

            try
            {
                Rect rect = sprite.rect;
                int width = Mathf.Max(1, Mathf.RoundToInt(rect.width));
                int height = Mathf.Max(1, Mathf.RoundToInt(rect.height));
                Texture2D result = new Texture2D(width, height, TextureFormat.RGBA32, false);
                Color[] pixels = readableSource.GetPixels(
                    Mathf.RoundToInt(rect.x),
                    Mathf.RoundToInt(rect.y),
                    width,
                    height);
                result.SetPixels(pixels);
                result.Apply();
                return result;
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(readableSource);
            }
        }

        private static Texture2D CopyTexture(Texture2D source)
        {
            RenderTexture temporary = RenderTexture.GetTemporary(
                source.width,
                source.height,
                0,
                RenderTextureFormat.ARGB32,
                RenderTextureReadWrite.Linear);
            RenderTexture previous = RenderTexture.active;

            try
            {
                UnityEngine.Graphics.Blit(source, temporary);
                RenderTexture.active = temporary;
                Texture2D result = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
                result.ReadPixels(new Rect(0, 0, source.width, source.height), 0, 0);
                result.Apply();
                return result;
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(temporary);
            }
        }

        private static string SanitizeFileName(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return "preview";
            }

            foreach (char invalid in Path.GetInvalidFileNameChars())
            {
                value = value.Replace(invalid, '_');
            }

            return value;
        }
    }
}
