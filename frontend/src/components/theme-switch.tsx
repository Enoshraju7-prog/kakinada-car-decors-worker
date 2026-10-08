import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sun, Moon } from "@/lib/icons";

export function ThemeSwitch() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      return localStorage.getItem("kcd-theme") === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("kcd-theme", theme);
    } catch {
      /* Preference storage is optional. */
    }
  }, [theme]);
  return (
    <Button
      variant="ghost"
      className="theme-switch"
      aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
      onClick={() => setTheme(theme === "light" ? "dark" : "light")}
    >
      {theme === "light" ? (
        <Moon aria-hidden="true" />
      ) : (
        <Sun aria-hidden="true" />
      )}
      <span className="button-label">
        {theme === "light" ? "Dark mode" : "Light mode"}
      </span>
    </Button>
  );
}
