export interface SiteConfig {
  backendUrl: string;
  productName: string;
  botUsername: string;
  contactEmail: string;
  githubUrl: string;
  mcpUrl: string;
}

function readEnv(key: string, fallback = ""): string {
  const value = import.meta.env[key as keyof ImportMetaEnv];
  return typeof value === "string" ? value.trim() : fallback;
}

export const config: SiteConfig = {
  backendUrl: readEnv("VITE_BACKEND_URL", "https://agentnotifier.duckdns.org").replace(/\/+$/, ""),
  productName: readEnv("VITE_PRODUCT_NAME", "Agent Notifier"),
  botUsername: readEnv("VITE_BOT_USERNAME"),
  contactEmail: readEnv("VITE_CONTACT_EMAIL"),
  githubUrl: readEnv("VITE_GITHUB_URL"),
  mcpUrl: "",
};

config.mcpUrl = config.backendUrl + "/mcp";
