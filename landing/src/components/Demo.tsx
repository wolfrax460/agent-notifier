import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";

const REPLIES: Record<string, string> = {
  yes: "Reply sent: “Yes, ship it.” Your AI continues with the deploy.",
  no: "Reply sent: “Not yet.” Your AI stops and waits for you.",
};

export function Demo() {
  const reduced = useReducedMotion();
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState("");

  function choose(reply: string) {
    setSelected(reply);
    setResult(REPLIES[reply] ?? "");
  }

  return (
    <div className="demo on-ink" role="group" aria-labelledby="demo-title">
      <div className="note__bar">
        <span className="note__icon" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14">
            <path d="M2.5 7.4l3 3L11.5 4" fill="none" stroke="#101A2E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="product">Agent Notifier</span>
        <span className="note__time">2m ago</span>
      </div>
      <p className="demo__title" id="demo-title">Deploy to production?</p>
      <p className="demo__body">Staging passed. Reply to continue.</p>
      <div className="demo__chips">
        <button
          className="chip"
          type="button"
          aria-pressed={selected === "yes"}
          onClick={() => choose("yes")}
        >
          Yes, ship it
        </button>
        <button
          className="chip"
          type="button"
          aria-pressed={selected === "no"}
          onClick={() => choose("no")}
        >
          Not yet
        </button>
      </div>
      <div className="demo__result" id="demo-result" aria-live="polite">
        <AnimatePresence mode="wait">
          {result && (
            <motion.span
              key={selected}
              initial={reduced ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? undefined : { opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {result}
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <AnimatePresence>
        {selected && (
          <motion.div
            className="demo__reply"
            initial={reduced ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            {selected === "yes" ? "Continuing the deploy..." : "Waiting for your go."}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
