import { motion, useReducedMotion } from "motion/react";
import { config } from "../config";

export function WorksW() {
  const reduced = useReducedMotion();
  const rows = [
    { tool: "Claude app (claude.ai, Claude Desktop)", how: "Custom connector with sign-in", note: "Custom connectors depend on your plan." },
    { tool: "ChatGPT", how: "Custom MCP connector with sign-in", note: "Needs a plan and settings that allow custom connectors." },
    { tool: "Claude Code", how: "One command, sign-in or token", note: "Also supports an automatic ping when a run ends." },
    { tool: "Codex CLI", how: "Config file and personal token", note: "Config syntax varies by version." },
    { tool: "OpenCode", how: "Config file and personal token", note: "Config syntax varies by version." },
    { tool: "Other MCP tools, including DeepSeek-based harnesses", how: "Server URL and personal token", note: "Works if the tool can reach a remote MCP server over HTTPS." },
    { tool: "Scripts, CI, tools without MCP", how: "One HTTP request", note: "POST to /api/notify." },
  ];
  return (
    <motion.section className="band" id="works-with" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>Works with</h2>
        <div>
          <table className="matrix">
            <thead>
              <tr>
                <th scope="col">Tool</th>
                <th scope="col">How it connects</th>
                <th scope="col">Good to know</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.tool}>
                  <th scope="row">{r.tool}</th>
                  <td data-label="How it connects">{r.how}</td>
                  <td data-label="Good to know">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>The model doesn't matter. Your tool makes the connection, so any model it runs can use this, including Claude, GPT, DeepSeek, Gemini and open models. The model does need to support tool calling.</p>
          <p>
            The service follows the MCP standard, and its sign-in and tools are covered by automated tests. Tools differ in which parts of MCP they support, so if one misbehaves, email{" "}
            <a className="contact" href={`mailto:${config.contactEmail}`}>{config.contactEmail}</a>.
          </p>
        </div>
      </div>
    </motion.section>
  );
}
