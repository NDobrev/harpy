import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { contrastRatio } from "./contrast";
import tokens from "./theme-tokens.json";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, "tokens.css"), "utf8");

const TEXT_BACKGROUNDS = [
  "background",
  "surface",
  "surface-raised",
  "code-background",
  "addition-background",
  "deletion-background",
] as const;

describe("theme tokens", () => {
  it("keeps CSS custom properties aligned with the JSON contract", () => {
    for (const [theme, values] of Object.entries(tokens.themes)) {
      expect(css).toContain(`[data-theme="${theme}"]`);
      for (const [name, value] of Object.entries(values)) {
        if (value.startsWith("rgba")) {
          continue;
        }
        expect(css.toLowerCase()).toContain(`${value.toLowerCase()}`);
        expect(css).toContain(`--${name}:`);
      }
    }
  });

  it("meets WCAG AA text contrast on semantic surfaces", () => {
    for (const [theme, values] of Object.entries(tokens.themes)) {
      for (const background of TEXT_BACKGROUNDS) {
        expect(
          contrastRatio(values.text, values[background]),
          `${theme} text on ${background}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
      expect(
        contrastRatio(values["text-muted"], values.background),
        `${theme} muted on background`,
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrastRatio(values["on-accent"], values.accent),
        `${theme} on-accent`,
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrastRatio(values.border, values.surface),
        `${theme} border on surface`,
      ).toBeGreaterThanOrEqual(3);
    }
  });
});
