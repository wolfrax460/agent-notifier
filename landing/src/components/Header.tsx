import { useEffect, useState } from "react";
import { config } from "../config";

export function Header() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const initial = saved === "light" ? "light" : "dark";
    setTheme(initial);
    document.documentElement.setAttribute("data-theme", initial);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  }

  return (
    <header className="wrap top">
      <a className="brand" href="#top">
        <span className="brand__mark" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14">
            <path d="M2.5 7.4l3 3L11.5 4" fill="none" stroke="#04180F" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="product">{config.productName}</span>
      </a>
      <nav className="top__nav" aria-label="Main">
        <a className="top__link" href="#how">How it works</a>
        <a className="top__link" href="#connect">Connect</a>
        <a className="top__link" href="#privacy">Privacy</a>
        <button className="btn btn--ghost btn--small" type="button" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        <a className="btn btn--ghost btn--small" href={config.backendUrl + "/login"}>Sign in</a>
      </nav>
    </header>
  );
}
