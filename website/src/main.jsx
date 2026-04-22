import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./theme.css";
import "./app.css";

const SESSION_UNLOCK_KEY = "human_ls_site_unlocked";
const KEYCHAIN_USERNAME = "human-ls-shared-access";

function SitePasscodeGate({ children }) {
  const expectedPasscode = import.meta.env.VITE_SITE_PASSCODE ?? "";
  const passcodeConfigured = expectedPasscode.length > 0;
  const [inputValue, setInputValue] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isUnlocked, setIsUnlocked] = useState(false);

  useEffect(() => {
    if (!passcodeConfigured) {
      setIsUnlocked(false);
      return;
    }

    try {
      setIsUnlocked(window.sessionStorage.getItem(SESSION_UNLOCK_KEY) === "true");
    } catch (_error) {
      setIsUnlocked(false);
    }
  }, [passcodeConfigured]);

  const handleSubmit = (event) => {
    event.preventDefault();

    if (!passcodeConfigured) {
      setErrorMessage("Die Seite ist nicht korrekt konfiguriert.");
      return;
    }

    if (inputValue === expectedPasscode) {
      try {
        window.sessionStorage.setItem(SESSION_UNLOCK_KEY, "true");
      } catch (_error) {
        // Ignore session storage errors and still unlock in-memory.
      }
      setIsUnlocked(true);
      setInputValue("");
      setErrorMessage("");
      return;
    }

    setErrorMessage("Passcode falsch. Bitte erneut versuchen.");
  };

  if (!passcodeConfigured) {
    return (
      <main className="site-gate">
        <section className="site-gate__card">
          <p className="eyebrow">Zugriff gesperrt</p>
          <h1>Passcode fehlt in der Konfiguration</h1>
          <p>
            Die Umgebungsvariable <code>VITE_SITE_PASSCODE</code> ist nicht gesetzt. Bitte als Admin
            setzen und neu deployen.
          </p>
        </section>
      </main>
    );
  }

  if (!isUnlocked) {
    return (
      <main className="site-gate">
        <section className="site-gate__card">
          <p className="eyebrow">Geschützter Bereich</p>
          <h1>Diese Seite ist passwortgeschützt.</h1>
          <form className="site-gate__form" onSubmit={handleSubmit} autoComplete="on">
            <input
              className="site-gate__sr-only"
              type="text"
              name="username"
              autoComplete="username"
              defaultValue={KEYCHAIN_USERNAME}
              tabIndex={-1}
              aria-hidden="true"
            />
            <label htmlFor="site-passcode">Passcode</label>
            <input
              id="site-passcode"
              name="password"
              type="password"
              value={inputValue}
              onChange={(event) => {
                setInputValue(event.target.value);
                setErrorMessage("");
              }}
              autoComplete="current-password"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect="off"
              required
            />
            <button type="submit">Entsperren</button>
          </form>
          {errorMessage ? <p className="site-gate__error">{errorMessage}</p> : null}
        </section>
      </main>
    );
  }

  return children;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <SitePasscodeGate>
      <App />
    </SitePasscodeGate>
  </React.StrictMode>,
);
