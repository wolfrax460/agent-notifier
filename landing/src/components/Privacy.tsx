import { motion, useReducedMotion } from "motion/react";
export function Privacy() {
  const reduced = useReducedMotion();
  return (
    <motion.section className="band" id="privacy" initial={reduced ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6 }}>
      <div className="wrap band__grid">
        <h2>Privacy and safety</h2>
        <div>
          <div className="split">
            <div>
              <h3>What we store</h3>
              <ul>
                <li>Your Telegram chat ID and first name.</li>
                <li>Access tokens, hashed, so we can't read them back.</li>
                <li>Replies you send to the bot, deleted after you read them or after 7 days.</li>
                <li>A daily count of messages sent, for the usage limit.</li>
              </ul>
            </div>
            <div>
              <h3>What we don't do</h3>
              <ul>
                <li>Log the text of your messages.</li>
                <li>Store email or WhatsApp passwords. Those channels exist only in the self-hosted version.</li>
                <li>Use your messages for anything except delivering them.</li>
              </ul>
            </div>
          </div>
          <p><strong>Know the limits.</strong> Telegram bot chats are not end-to-end encrypted, and your messages pass through this server and Telegram. Don't send passwords, API keys or private code.</p>
          <p><strong>Sign-in is checked twice.</strong> The bot shows the IP address and device that asked to sign in, and nothing happens until you tap Confirm. If someone sent you the link, tap Deny.</p>
          <p><strong>Delete everything any time.</strong> Send <code>/delete confirm</code> to the bot, or use Delete account in your dashboard. Your account, tokens and stored replies are removed.</p>
          <p>This website sets no cookies and runs no analytics. Its fonts load from Google Fonts.</p>
        </div>
      </div>
    </motion.section>
  );
}
