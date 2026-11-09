import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";

const ITEMS = [
  { q: "Does it cost anything?", a: "No. Accounts are free, with limits of 10 messages a minute and 300 a day." },
  { q: "Can my AI read my Telegram chats?", a: "No. It can only read messages you send to this bot, and only through ask_me or check_inbox." },
  { q: "Which AI models work?", a: "Any model your tool runs, as long as it supports tool calling. The connection is made by the tool, not the model." },
  { q: "My tool has no MCP support.", a: "Use the HTTP request from a script or hook. The Scripts and others tab shows the command." },
  { q: "The connector won't connect.", a: "Check that the URL ends in /mcp and opens over HTTPS. Setup steps change between tool versions, so also check your tool's MCP docs. Still stuck? Email support." },
  { q: "Can I get ntfy push notifications too?", a: "Yes. Turn on ntfy in your dashboard, install the free ntfy app, and subscribe to the topic it shows. ntfy is send-only, so replies still go through Telegram." },
];

export function Faq() {
  const reduced = useReducedMotion();
  const [open, setOpen] = useState<number | null>(null);
  return (
    <motion.section className="band" id="faq" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>Questions</h2>
        <div className="faq">
          {ITEMS.map((it, i) => {
            const isOpen = open === i;
            return (
              <div className="faq__item" key={it.q}>
                <button
                  className="faq__button"
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={`faq-panel-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  {it.q}
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      id={`faq-panel-${i}`}
                      className="faq__panel"
                      initial={reduced ? false : { height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={reduced ? undefined : { height: 0, opacity: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <div className="faq__panel-inner">
                        <p>{it.a}</p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
