namespace UnityResourceRag.Editor
{
    public sealed class UnityResourceRagAuthProfileInfo
    {
        public string Title { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public string NextStep { get; set; } = string.Empty;
        public bool ShowApiKeyEnvField { get; set; }
        public bool ShowCodexAuthOverrideField { get; set; }
    }

    public static class UnityResourceRagAuthProfilePresenter
    {
        public static UnityResourceRagAuthProfileInfo Describe(UnityResourceRagEditorSettings settings)
        {
            switch (settings.AuthMode)
            {
                case UnityResourceRagAuthMode.UseApiKeyEnvironmentVariable:
                    return new UnityResourceRagAuthProfileInfo
                    {
                        Title = "Use an API key from my environment",
                        Summary = "Choose this when you already manage provider keys outside Unity. The key itself stays in your shell or OS environment, and Unity only stores the environment variable name.",
                        NextStep = "Keep the variable name below aligned with your existing setup. In most cases `OPENAI_API_KEY` is the right default.",
                        ShowApiKeyEnvField = true,
                    };
                case UnityResourceRagAuthMode.OfflineLocal:
                    return new UnityResourceRagAuthProfileInfo
                    {
                        Title = "Stay offline with local fallback",
                        Summary = "Choose this when you want to validate cataloging, draft generation, and Unity apply without relying on a hosted model.",
                        NextStep = "This is the safest first-run fallback when you only want to confirm that the local pipeline works.",
                    };
                default:
                    return new UnityResourceRagAuthProfileInfo
                    {
                        Title = "Use my current Codex sign-in",
                        Summary = "Recommended for most users. If you are already signed in to Codex, Unity Resource RAG will reuse that sign-in instead of asking you to paste a key into Unity.",
                        NextStep = settings.HasReadableCodexAuthFile
                            ? "Your current sign-in file was found. You can keep the default setup unless you need a custom auth file location."
                            : "If the default Codex auth file is not found, you can still continue, sign in to Codex again, or point the window to a custom auth file path in Advanced Paths & Overrides.",
                        ShowCodexAuthOverrideField = true,
                    };
            }
        }
    }
}
