import { AlertTriangle, Check, FileDiff, HelpCircle } from "lucide-react";
import { useEffect, useState } from "react";

import tokens from "./theme-tokens.json";
import styles from "./gallery.module.css";

export type ThemeId = keyof typeof tokens.themes;

const THEMES = Object.keys(tokens.themes) as ThemeId[];

function isThemeId(value: string | null): value is ThemeId {
  return value === "white" || value === "black" || value === "dark_blue";
}

function applyTheme(theme: ThemeId): void {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem("harpy.theme", theme);
}

export function Gallery() {
  const [theme, setTheme] = useState<ThemeId>(() => {
    const stored = window.localStorage.getItem("harpy.theme");
    return isThemeId(stored) ? stored : "dark_blue";
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <h1>Harpy theme gallery</h1>
          <p>Seeded review chrome for White, Black, and Dark Blue. No live analysis.</p>
        </div>
        <div className={styles.themeSwitch} role="group" aria-label="Theme">
          {THEMES.map((id) => (
            <button
              key={id}
              type="button"
              className={id === theme ? styles.primary : styles.button}
              aria-pressed={id === theme}
              onClick={() => setTheme(id)}
            >
              {id.replace("_", " ")}
            </button>
          ))}
        </div>
      </header>

      <div className={styles.workspace}>
        <section className={`${styles.panel} ${styles.region}`} aria-labelledby="changes-heading">
          <h2 id="changes-heading">Changes</h2>
          <article className={styles.change}>
            <strong>C1 Auth gate now requires org membership</strong>
            <p className={styles.meta}>
              importance 82 · unexpectedness 44 · confidence 70% ·{" "}
              <span className={styles.badge}>blocker</span>
            </p>
          </article>
          <article className={styles.change}>
            <strong>C2 Generated lockfile refresh</strong>
            <p className={styles.meta}>noise · 1 file · unreviewed</p>
          </article>
        </section>

        <section className={`${styles.panel} ${styles.region}`} aria-labelledby="evidence-heading">
          <h2 id="evidence-heading">Evidence</h2>
          <p className={styles.meta}>
            <FileDiff size={16} aria-hidden="true" /> Unified diff · src/auth/permissions.py
          </p>
          <div className={styles.diff} role="table" aria-label="Unified diff">
            <div className={styles.row} role="row">
              <span className={styles.gutter}>10</span>
              <span className={styles.gutter}>10</span>
              <span className={styles.marker}> </span>
              <span>def can_review(user, org):</span>
            </div>
            <div className={`${styles.row} ${styles.deletion}`} role="row">
              <span className={styles.gutter}>11</span>
              <span className={styles.gutter}></span>
              <span className={styles.marker}>−</span>
              <span> return user.is_staff</span>
            </div>
            <div className={`${styles.row} ${styles.addition}`} role="row">
              <span className={styles.gutter}></span>
              <span className={styles.gutter}>11</span>
              <span className={styles.marker}>+</span>
              <span> return user.is_staff or org.has_member(user)</span>
            </div>
          </div>
        </section>

        <section
          className={`${styles.panel} ${styles.region} ${styles.inspector}`}
          aria-labelledby="inspector-heading"
        >
          <h2 id="inspector-heading">Inspector</h2>
          <p>Before: staff-only access. After: organization membership is also sufficient.</p>
          <p className={styles.meta}>Not assessed for security impact in this static report.</p>
        </section>
      </div>

      <section
        className={`${styles.panel} ${styles.dialog}`}
        style={{ marginTop: 24 }}
        aria-labelledby="scope-heading"
      >
        <h2 id="scope-heading">Analysis configuration</h2>
        <p>Grouped checks first. Start stays disabled until a server plan exists.</p>
        <label>
          <input type="checkbox" defaultChecked /> Logical changes
        </label>
        <label>
          <input type="checkbox" defaultChecked /> Security
        </label>
        <div className={styles.buttonRow}>
          <button type="button" className={styles.button}>
            Cancel
          </button>
          <button type="button" className={styles.primary} disabled>
            Start analysis
          </button>
        </div>
      </section>

      <section
        className={`${styles.panel} ${styles.dialog}`}
        style={{ marginTop: 24 }}
        aria-labelledby="conflict-heading"
      >
        <h2 id="conflict-heading">Note conflict</h2>
        <div className={styles.conflict}>
          <div className={styles.inset}>
            <h3>Your edit</h3>
            <p>Need a test for the org membership branch.</p>
          </div>
          <div className={styles.inset}>
            <h3>Current shared value</h3>
            <p>Ask whether guests can inherit membership from a parent org.</p>
          </div>
        </div>
        <div className={styles.buttonRow}>
          <button type="button" className={styles.button}>
            Keep editing
          </button>
          <button type="button" className={styles.button}>
            Use current
          </button>
          <button type="button" className={styles.primary}>
            Replace with my edit
          </button>
        </div>
      </section>

      <section
        className={`${styles.panel} ${styles.dialog}`}
        style={{ marginTop: 24 }}
        aria-labelledby="error-heading"
      >
        <h2 id="error-heading">
          <AlertTriangle size={18} aria-hidden="true" /> Error
        </h2>
        <p className={styles.error} role="alert">
          GitHub credentials are not provisioned for this user. History remains available.
        </p>
        <button type="button" className={styles.button}>
          Retry refresh
        </button>
      </section>

      <section
        className={`${styles.panel} ${styles.dialog}`}
        style={{ marginTop: 24 }}
        aria-labelledby="empty-heading"
      >
        <h2 id="empty-heading">Empty report</h2>
        <p className={styles.empty}>
          <HelpCircle size={16} aria-hidden="true" /> None found within assessed context.
        </p>
        <p>
          <Check size={16} aria-hidden="true" /> Static ranking is ready. Semantic analysis has not
          started.
        </p>
      </section>

      <nav className={styles.phoneNav} aria-label="Workspace regions">
        <button type="button" className={styles.button}>
          Changes
        </button>
        <button type="button" className={styles.button}>
          Evidence
        </button>
        <button type="button" className={styles.button}>
          Inspector
        </button>
      </nav>
    </div>
  );
}
