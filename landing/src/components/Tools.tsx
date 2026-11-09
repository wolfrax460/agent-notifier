import { motion, useReducedMotion } from "motion/react";
export function Tools() {
  const reduced = useReducedMotion();
  return (
    <motion.section className="band" id="tools" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>What your AI can do</h2>
        <dl className="tools">
          <div>
            <dt><code>notify_me</code></dt>
            <dd>Sends you a message. Low and normal priority go to Telegram. High and urgent also go to ntfy if you turned it on.</dd>
          </div>
          <div>
            <dt><code>ask_me</code></dt>
            <dd>Asks a question and waits up to four minutes for your reply in Telegram. If you don't answer, your AI continues with a safe assumption and tells you.</dd>
          </div>
          <div>
            <dt><code>check_inbox</code></dt>
            <dd>Reads the messages you sent to the bot while it was working.</dd>
          </div>
          <div>
            <dt><code>channel_status</code></dt>
            <dd>Shows which channels are on and how many messages you've sent today.</dd>
          </div>
        </dl>
      </div>
    </motion.section>
  );
}
