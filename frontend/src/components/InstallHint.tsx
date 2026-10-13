import { useState } from "react";

const DISMISSED_KEY = "snowflights.installHintDismissed";

/** iPhone/iPad Safari that isn't already running from the Home Screen. */
export function shouldShowInstallHint(nav: Navigator = navigator, win: Window = window): boolean {
  const ios = /iPhone|iPad|iPod/.test(nav.userAgent) || (nav.platform === "MacIntel" && nav.maxTouchPoints > 1);
  const standalone =
    (nav as Navigator & { standalone?: boolean }).standalone === true ||
    win.matchMedia?.("(display-mode: standalone)").matches === true;
  return ios && !standalone;
}

function dismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function InstallHint() {
  const [show, setShow] = useState(() => shouldShowInstallHint() && !dismissed());
  if (!show) return null;
  const dismiss = () => {
    setShow(false);
    try {
      window.localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // Storage unavailable; the hint just comes back next visit.
    }
  };
  return (
    <aside className="install-hint" aria-label="Install on your iPhone">
      <p>
        <strong>Use it like an app:</strong> tap the Share button{" "}
        <svg className="share-icon" viewBox="0 0 16 20" width="14" height="17" aria-label="Share">
          <path d="M8 1v12M4 5l4-4 4 4M3 9H1.5v9.5h13V9H13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>{" "}
        then <strong>Add to Home Screen</strong>.
      </p>
      <button type="button" className="link-button" onClick={dismiss}>
        Dismiss
      </button>
    </aside>
  );
}
