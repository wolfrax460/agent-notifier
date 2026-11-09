import { motion, useReducedMotion } from "motion/react";

const STEPS = [
  { n: "1", title: "Sign in with Telegram", body: "Press Start on the bot, then tap Confirm in the chat. No password, no email." },
  { n: "2", title: "Add the connector to your AI tool", body: "Paste the server URL into your tool. If it supports sign-in, it asks you to approve once. Otherwise use a personal token from your dashboard." },
  { n: "3", title: "Start a task and walk away", body: "Your AI calls notify_me when it finishes, or ask_me when it needs an answer. You reply in Telegram." },
];

export function HowItWorks() {
  const reduced = useReducedMotion();
  return (
    <motion.section className="band" id="how" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>How it works</h2>
        <div style={{ position: "relative" }}>
          <svg
            className="steps-line"
            viewBox="0 0 4 100"
            preserveAspectRatio="none"
            aria-hidden="true"
            style={{ position: "absolute", left: "1.5rem", top: "3rem", bottom: "1rem", width: "2px", height: "calc(100% - 4rem)", transform: "translateX(-50%)" }}
          >
            <motion.line
              x1="2"
              y1="0"
              x2="2"
              y2="100"
              stroke="var(--line)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
              initial={reduced ? false : { pathLength: 0 }}
              whileInView={{ pathLength: 1 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.9, ease: "easeInOut" }}
            />
          </svg>
          <ol className="steps">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="steps__n" aria-hidden="true">{s.n}</span>
                <div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </motion.section>
  );
}
