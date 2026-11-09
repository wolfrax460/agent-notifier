import { motion, useReducedMotion } from "motion/react";

const CARDS = [
  { tool: "Claude Code", msg: "Tests pass. 3 files changed.", time: "2m ago" },
  { tool: "Codex CLI", msg: "Refactor complete. PR ready.", time: "5m ago" },
  { tool: "OpenCode", msg: "Build failed. Exit code 1.", time: "8m ago" },
  { tool: "CI script", msg: "Deploy to production?", time: "12m ago" },
];

export function NotificationStack() {
  const reduced = useReducedMotion();
  return (
    <motion.section className="wrap" aria-label="Recent notifications" style={{ paddingBottom: "var(--gap)" }} initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="notif-stack">
        {CARDS.map((c, i) => (
          <motion.div
            key={c.tool}
            className="notif-card on-ink"
            initial={reduced ? false : { opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.35, delay: reduced ? 0 : i * 0.08, ease: "easeOut" }}
          >
            <span className="notif-card__icon" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 14 14">
                <path d="M2.5 7.4l3 3L11.5 4" fill="none" stroke="#101A2E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span>{c.tool}</span>
            <span style={{ color: "#D9DFEA", fontWeight: 400 }}>{c.msg}</span>
            <span className="notif-card__meta">{c.time}</span>
          </motion.div>
        ))}
      </div>
    </motion.section>
  );
}
