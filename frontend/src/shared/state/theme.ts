import { create } from "zustand";
export type Theme = "light" | "dark";
export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("erp-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage may be unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}
function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}
export const useTheme = create<{ theme: Theme; toggle: () => void }>(
  (set, get) => ({
    theme: initialTheme(),
    toggle: () => {
      const theme = get().theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("erp-theme", theme);
      } catch {
        /* Optional persistence */
      }
      apply(theme);
      set({ theme });
    },
  }),
);
apply(useTheme.getState().theme);
window.addEventListener("storage", (e) => {
  if (e.key === "erp-theme") {
    const theme = initialTheme();
    apply(theme);
    useTheme.setState({ theme });
  }
});
