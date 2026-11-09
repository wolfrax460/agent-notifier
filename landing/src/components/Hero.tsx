import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion, useInView } from "motion/react";
import { useRef } from "react";
import { config } from "../config";
import { Demo } from "./Demo";

const MESSAGES = [
  "Tests pass. 3 files changed. Took 4m 12s.",
  "Deploy needs a decision.",
  "Build failed. Exit code 1.",
  "Refactor done. 12 tests added.",
];

export function Hero() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.3 });
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    if (reduced || !inView) return;
    const id = window.setInterval(() => {
      setMsgIndex((i) => (i + 1) % MESSAGES.length);
    }, 2600);
    return () => window.clearInterval(id);
  }, [reduced, inView]);

  const shownIndex = reduced ? 0 : msgIndex;

  return (
    <section className="hero" aria-labelledby="hero-title" id="top" ref={ref}>
      <div className="wrap">
        <motion.div
          className="note on-ink"
          initial={reduced ? false : { opacity: 0, y: -30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
        >
          <div className="note__bar">
            <span className="note__icon" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 14 14">
                <path d="M2.5 7.4l3 3L11.5 4" fill="none" stroke="#101A2E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {!reduced && (
                <motion.span
                  className="ping-ring"
                  initial={{ opacity: 0.9, scale: 0.6 }}
                  animate={{ opacity: 0, scale: 1.9 }}
                  transition={{ duration: 0.9, delay: 0.15, ease: "easeOut" }}
                />
              )}
            </span>
            <span className="product">{config.productName}</span>
            <span className="note__time">now</span>
          </div>
          <h1 className="note__title" id="hero-title">Your AI finished the job.</h1>
          <div className="note__body" aria-live="polite">
            <AnimatePresence mode="wait">
              <motion.span
                key={shownIndex}
                initial={reduced ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={reduced ? undefined : { opacity: 0 }}
                transition={{ duration: 0.25 }}
              >
                {MESSAGES[shownIndex]}
              </motion.span>
            </AnimatePresence>
          </div>
        </motion.div>

        <div className="intro">
          <div>
            <p className="intro__lead">
              <span className="product">{config.productName}</span> messages you on Telegram when your AI agent is done, or when it needs a decision. Start a long task, step away, and get pinged.
            </p>
            <p>Works with Claude, ChatGPT, Codex CLI, OpenCode, and any tool that can connect to an MCP server.</p>
            <div className="intro__cta">
              <a className="btn btn--primary" href="#connect">Connect your AI tool</a>
              <a className="btn btn--ghost" href={config.backendUrl + "/login"}>Sign in with Telegram</a>
            </div>
            <p className="fine">Free, with limits of 10 messages a minute and 300 a day.</p>
          </div>
          <div>
            <Demo />
            <p className="demo__caption">Try it. This is how your AI asks you a question and waits for the answer.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
