import React, { useState, useRef } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { config } from "../config";

type TabId = "claude" | "chatgpt" | "claudecode" | "codex" | "opencode" | "script";

const TABS: { id: TabId; label: string }[] = [
  { id: "claude", label: "Claude app" },
  { id: "chatgpt", label: "ChatGPT" },
  { id: "claudecode", label: "Claude Code" },
  { id: "codex", label: "Codex CLI" },
  { id: "opencode", label: "OpenCode" },
  { id: "script", label: "Scripts and others" },
];

function CodeBox({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }
  return (
    <div className="codebox">
      <button className={`copy ${copied ? "copied" : ""}`} type="button" onClick={copy}>
        {copied ? "Copied" : "Copy"}
      </button>
      <pre className="code">
        <code>{children}</code>
      </pre>
    </div>
  );
}

export function ConnectTabs() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState<TabId>("claude");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function select(id: TabId, focus = false) {
    setActive(id);
    if (focus) tabRefs.current[id]?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: TabId | null = null;
    if (e.key === "ArrowRight") next = TABS[(index + 1) % TABS.length]!.id;
    else if (e.key === "ArrowLeft") next = TABS[(index - 1 + TABS.length) % TABS.length]!.id;
    else if (e.key === "Home") next = TABS[0]!.id;
    else if (e.key === "End") next = TABS[TABS.length - 1]!.id;
    if (next) {
      e.preventDefault();
      select(next, true);
    }
  }

  const mcp = config.mcpUrl;
  const backend = config.backendUrl;

  return (
    <motion.section className="band" id="connect" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>Connect your tool</h2>
        <div className="tabs">
          <div className="tabs__list" role="tablist" aria-label="Choose your tool">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                ref={(el) => (tabRefs.current[t.id] = el)}
                className="tab"
                role="tab"
                id={`tab-${t.id}`}
                aria-controls={`panel-${t.id}`}
                aria-selected={active === t.id}
                tabIndex={active === t.id ? 0 : -1}
                onClick={() => select(t.id)}
                onKeyDown={(e) => onKeyDown(e, i)}
              >
                {active === t.id && !reduced && (
                  <motion.span
                    className="tab-indicator"
                    layoutId="tab-indicator"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                {active === t.id && reduced && <span className="tab-indicator" />}
                <span style={{ position: "relative", zIndex: 1 }}>{t.label}</span>
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              role="tabpanel"
              id={`panel-${active}`}
              aria-labelledby={`tab-${active}`}
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduced ? undefined : { opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {active === "claude" && (
                <>
                  <ol>
                    <li>Open Settings, then Connectors, and add a custom connector.</li>
                    <li>Paste this URL:</li>
                  </ol>
                  <CodeBox>{mcp}</CodeBox>
                  <ol start={3}>
                    <li>Sign in with Telegram when asked, then tap Allow.</li>
                  </ol>
                  <p className="note-inline">Works in claude.ai and Claude Desktop. Custom connectors depend on your plan.</p>
                </>
              )}
              {active === "chatgpt" && (
                <>
                  <ol>
                    <li>In ChatGPT's connector or developer settings, add a custom MCP connector.</li>
                    <li>Paste this URL and choose OAuth as the sign-in method:</li>
                  </ol>
                  <CodeBox>{mcp}</CodeBox>
                  <ol start={3}>
                    <li>Sign in with Telegram when asked, then tap Allow.</li>
                  </ol>
                  <p className="note-inline">Custom MCP connectors need a ChatGPT plan and settings that allow them. Where they appear changes over time.</p>
                </>
              )}
              {active === "claudecode" && (
                <>
                  <p>Add the server, then run <code>/mcp</code> inside Claude Code and choose to sign in:</p>
                  <CodeBox>{`claude mcp add --transport http agent-notifier ${mcp}`}</CodeBox>
                  <p>Prefer a token? Create one in your <a href={config.backendUrl + "/app"}>dashboard</a> and use:</p>
                  <CodeBox>{`claude mcp add --transport http agent-notifier ${mcp} \\\n  --header "Authorization: Bearer an_pat_YOUR_TOKEN"`}</CodeBox>
                  <p>To get a ping every time a run ends, without relying on the model, add a Stop hook to <code>~/.claude/settings.json</code>:</p>
                  <CodeBox>{`{\n  "hooks": {\n    "Stop": [\n      { "hooks": [ {\n        "type": "command",\n        "command": "curl -s -X POST ${backend}/api/notify -H \\"Authorization: Bearer $AGENT_NOTIFIER_TOKEN\\" -H \\"Content-Type: application/json\\" -d '{\\"message\\":\\"Claude Code finished\\"}'"\n      } ] }\n    ]\n  }\n}`}</CodeBox>
                  <p className="note-inline">Set <code>AGENT_NOTIFIER_TOKEN</code> in your shell profile. If you use both the hook and the MCP tool, you may get two messages, so pick one. On Windows, run Claude Code in WSL or adapt the quoting.</p>
                </>
              )}
              {active === "codex" && (
                <>
                  <p>Create a token in your <a href={config.backendUrl + "/app"}>dashboard</a>, put it in an environment variable, and add this to <code>~/.codex/config.toml</code>:</p>
                  <CodeBox>{`[mcp_servers.agent-notifier]\nurl = "${mcp}"\nbearer_token_env_var = "AGENT_NOTIFIER_TOKEN"`}</CodeBox>
                  <p className="note-inline">Config keys change between Codex versions. If this doesn't load, check the MCP section of the Codex docs.</p>
                </>
              )}
              {active === "opencode" && (
                <>
                  <p>Create a token in your <a href={config.backendUrl + "/app"}>dashboard</a>, save it in an environment variable named <code>AGENT_NOTIFIER_TOKEN</code>, and add this to your OpenCode config:</p>
                  <CodeBox>{`{\n  "$schema": "https://opencode.ai/config.json",\n  "mcp": {\n    "servers": {\n      "agent-notifier": {\n        "type": "remote",\n        "url": "${mcp}",\n        "oauth": false,\n        "headers": { "Authorization": "Bearer {env:AGENT_NOTIFIER_TOKEN}" }\n      }\n    }\n  }\n}`}</CodeBox>
                  <p className="note-inline">Older OpenCode versions list servers directly under <code>mcp</code> instead of <code>mcp.servers</code>. If it doesn't load, check the MCP page of the OpenCode docs for your version.</p>
                </>
              )}
              {active === "script" && (
                <>
                  <p>Any tool that can run a command or call a URL can send a message. Create a token in your <a href={config.backendUrl + "/app"}>dashboard</a>, then:</p>
                  <CodeBox>{`curl -X POST ${backend}/api/notify \\\n  -H "Authorization: Bearer an_pat_YOUR_TOKEN" \\\n  -H "Content-Type: application/json" \\\n  -d '{"message":"Build finished","title":"CI","priority":"high"}'`}</CodeBox>
                  <p>Priority is <code>low</code>, <code>normal</code>, <code>high</code> or <code>urgent</code>. For tools with MCP support that aren't listed here, use the server URL {mcp} with the same token as a Bearer header.</p>
                </>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </motion.section>
  );
}
