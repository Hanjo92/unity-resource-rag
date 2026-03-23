using System;
using System.IO;
using System.Text;
using MCPForUnity.External.Tommy;

namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagCodexConfigResult
    {
        public bool Success { get; set; }
        public bool Skipped { get; set; }
        public string Summary { get; set; } = string.Empty;
        public string ConfigPath { get; set; } = string.Empty;
    }

    public static class UnityResourceRagCodexConfigSync
    {
        private const string ServerKey = "unityResourceRag";

        public static UnityResourceRagCodexConfigResult EnsureSidecarServer(UnityResourceRagEditorSettings settings)
        {
            settings.EnsureDefaults();
            string configPath = settings.CodexConfigPath;

            if (!UnityResourceRagEditorSettings.IsSidecarRuntimeRoot(settings.SidecarRepoRoot))
            {
                return new UnityResourceRagCodexConfigResult
                {
                    Skipped = true,
                    Summary = "Skipped Codex config sync because the sidecar runtime root could not be found.",
                    ConfigPath = configPath,
                };
            }

            string existingToml = string.Empty;
            if (File.Exists(configPath))
            {
                try
                {
                    existingToml = File.ReadAllText(configPath);
                }
                catch (Exception ex)
                {
                    return new UnityResourceRagCodexConfigResult
                    {
                        Summary = $"Failed to read the Codex config: {ex.Message}",
                        ConfigPath = configPath,
                    };
                }
            }

            TomlTable root = TryParseToml(existingToml) ?? new TomlTable();
            TomlTable mcpServers = EnsureTable(root, "mcp_servers");
            mcpServers[ServerKey] = CreateSidecarTable(settings);

            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(configPath) ?? string.Empty);
                using var writer = new StringWriter();
                root.WriteTo(writer);
                WriteAtomicFile(configPath, writer.ToString());
            }
            catch (Exception ex)
            {
                return new UnityResourceRagCodexConfigResult
                {
                    Summary = $"Failed to write the Codex config: {ex.Message}",
                    ConfigPath = configPath,
                };
            }

            return new UnityResourceRagCodexConfigResult
            {
                Success = true,
                Summary = $"Synced the `{ServerKey}` MCP server entry into the Codex config.",
                ConfigPath = configPath,
            };
        }

        private static TomlTable CreateSidecarTable(UnityResourceRagEditorSettings settings)
        {
            var table = new TomlTable
            {
                ["command"] = new TomlString { Value = settings.PythonExecutable },
                ["cwd"] = new TomlString { Value = settings.SidecarRepoRoot },
                ["startup_timeout_sec"] = new TomlInteger { Value = 60 },
            };

            var args = new TomlArray();
            args.Add(new TomlString { Value = "-m" });
            args.Add(new TomlString { Value = "pipeline.mcp" });
            table["args"] = args;
            return table;
        }

        private static TomlTable EnsureTable(TomlTable root, string key)
        {
            if (!root.TryGetNode(key, out TomlNode node) || node is not TomlTable table)
            {
                table = new TomlTable();
                root[key] = table;
            }

            return table;
        }

        private static TomlTable TryParseToml(string rawToml)
        {
            if (string.IsNullOrWhiteSpace(rawToml))
            {
                return null;
            }

            try
            {
                using var reader = new StringReader(rawToml);
                return TOML.Parse(reader);
            }
            catch
            {
                return null;
            }
        }

        private static void WriteAtomicFile(string path, string contents)
        {
            string tempPath = path + ".tmp";
            string backupPath = path + ".backup";

            File.WriteAllText(tempPath, contents, new UTF8Encoding(false));
            try
            {
                File.Replace(tempPath, path, backupPath);
            }
            catch (FileNotFoundException)
            {
                File.Move(tempPath, path);
            }
        }
    }
}
