"use client";

import { ThemeProvider as NextThemes } from "next-themes";

/**
 * Theme root.
 *
 * `defaultTheme="light"` rather than "system" is deliberate. This is a
 * document-shaped tool — dense tables of quoted patent text — and light is the
 * register people expect to read that in. Following the OS silently meant
 * anyone with dark mode on got a dark app with no way to change it.
 * "system" is still offered explicitly in the toggle.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemes
      attribute="data-theme"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemes>
  );
}
