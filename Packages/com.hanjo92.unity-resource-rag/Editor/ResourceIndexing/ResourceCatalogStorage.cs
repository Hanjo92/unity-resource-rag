using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace UnityResourceRag.Editor.ResourceIndexing
{
    /// <summary>
    /// Handles catalog path resolution and JSONL persistence outside the Assets folder.
    /// </summary>
    public static class ResourceCatalogStorage
    {
        public const string DefaultCatalogRelativePath = "Library/ResourceRag/resource_catalog.jsonl";
        public const string DefaultManifestRelativePath = "Library/ResourceRag/resource_catalog_manifest.json";
        public const string DefaultPreviewRelativePath = "Library/ResourceRag/previews";

        public static string GetProjectRoot()
        {
            return Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
        }

        public static string ResolveProjectPath(string requestedPath, string defaultRelativePath)
        {
            string projectRoot = GetProjectRoot();
            string candidate = string.IsNullOrWhiteSpace(requestedPath) ? defaultRelativePath : requestedPath;
            if (Path.IsPathRooted(candidate))
            {
                return Path.GetFullPath(candidate).Replace('\\', '/');
            }

            return Path.GetFullPath(Path.Combine(projectRoot, candidate)).Replace('\\', '/');
        }

        public static void EnsureParentDirectory(string filePath)
        {
            string directory = Path.GetDirectoryName(filePath);
            if (!string.IsNullOrWhiteSpace(directory) && !Directory.Exists(directory))
            {
                Directory.CreateDirectory(directory);
            }
        }

        public static ResourceCatalogManifest WriteCatalog(
            IReadOnlyList<ResourceCatalogRecord> records,
            string catalogPath,
            string manifestPath,
            string previewDirectory)
        {
            EnsureParentDirectory(catalogPath);
            EnsureParentDirectory(manifestPath);

            using (var writer = new StreamWriter(catalogPath, false))
            {
                for (int i = 0; i < records.Count; i++)
                {
                    writer.WriteLine(JsonConvert.SerializeObject(records[i], Formatting.None));
                }
            }

            var manifest = new ResourceCatalogManifest
            {
                generatedAtUtc = DateTime.UtcNow.ToString("o"),
                catalogPath = catalogPath,
                previewDirectory = previewDirectory,
                recordCount = records.Count,
                assetCounts = records
                    .GroupBy(record => record.assetType ?? "Unknown")
                    .ToDictionary(group => group.Key, group => group.Count())
            };

            File.WriteAllText(manifestPath, JsonConvert.SerializeObject(manifest, Formatting.Indented));
            return manifest;
        }

        public static bool TryReadCatalogPage(
            string catalogPath,
            string assetTypeFilter,
            string queryFilter,
            int pageSize,
            int pageNumber,
            out List<ResourceCatalogRecord> page,
            out int totalCount,
            out string error)
        {
            page = new List<ResourceCatalogRecord>();
            totalCount = 0;
            error = null;

            if (!File.Exists(catalogPath))
            {
                error = $"Catalog file not found: {catalogPath}";
                return false;
            }

            var allRecords = new List<ResourceCatalogRecord>();
            string normalizedAssetType = string.IsNullOrWhiteSpace(assetTypeFilter)
                ? null
                : assetTypeFilter.Trim();
            string normalizedQuery = string.IsNullOrWhiteSpace(queryFilter)
                ? null
                : queryFilter.Trim().ToLowerInvariant();

            foreach (string line in File.ReadLines(catalogPath))
            {
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                ResourceCatalogRecord record = JsonConvert.DeserializeObject<ResourceCatalogRecord>(line);
                if (record == null)
                {
                    continue;
                }

                if (!string.IsNullOrWhiteSpace(normalizedAssetType) &&
                    !string.Equals(record.assetType, normalizedAssetType, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (!string.IsNullOrWhiteSpace(normalizedQuery))
                {
                    string haystack = string.Join(" ", new[]
                    {
                        record.name ?? string.Empty,
                        record.path ?? string.Empty,
                        record.semanticText ?? string.Empty
                    }).ToLowerInvariant();

                    if (!haystack.Contains(normalizedQuery))
                    {
                        continue;
                    }
                }

                allRecords.Add(record);
            }

            totalCount = allRecords.Count;
            int safePageSize = Math.Max(1, pageSize);
            int safePageNumber = Math.Max(1, pageNumber);
            page = allRecords
                .Skip((safePageNumber - 1) * safePageSize)
                .Take(safePageSize)
                .ToList();
            return true;
        }
    }
}
