import { config } from "../config";

export function Footer() {
  return (
    <footer className="foot">
      <div className="wrap foot__row">
        <span>
          <span className="product">{config.productName}</span>. Independent project, not affiliated with Anthropic, OpenAI or Telegram.
        </span>
        <span>
          <a href={config.backendUrl + "/app"}>Dashboard</a> &nbsp;
          <a href="#privacy">Privacy</a> &nbsp;
          {config.githubUrl && (
            <>
              <a className="source-link" href={config.githubUrl}>Source</a> &nbsp;
            </>
          )}
          <a className="contact" href={`mailto:${config.contactEmail}`}>{config.contactEmail}</a>
        </span>
      </div>
    </footer>
  );
}
