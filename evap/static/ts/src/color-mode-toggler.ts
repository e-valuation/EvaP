/*!
 * Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
 * Copyright 2011-2025 The Bootstrap Authors
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
    "use strict";

    type Theme = "light" | "dark" | "auto";
    const isTheme = (value: string | null): value is Theme => value === "light" || value === "dark" || value === "auto";

    const getStoredTheme = (): Theme | null => {
        const item = localStorage.getItem("theme");
        return isTheme(item) ? item : null;
    };
    const setStoredTheme = (theme: Theme): void => localStorage.setItem("theme", theme);

    const getPreferredTheme = (): Theme => {
        const storedTheme = getStoredTheme();
        if (storedTheme) {
            return storedTheme;
        }

        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    };

    const setTheme = (theme: Theme): void => {
        if (theme === "auto") {
            document.documentElement.setAttribute(
                "data-bs-theme",
                window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
            );
        } else {
            document.documentElement.setAttribute("data-bs-theme", theme);
        }
    };

    setTheme(getPreferredTheme());

    const showActiveTheme = (theme: Theme, focus = false): void => {
        const themeSwitcher = document.querySelector<HTMLElement>("#bd-theme");

        if (!themeSwitcher) {
            return;
        }

        const themeSwitcherText = document.querySelector<HTMLElement>("#bd-theme-text");
        const activeThemeIcon = document.querySelector<SVGUseElement>(".theme-icon-active use");
        const btnToActive = document.querySelector<HTMLElement>(`[data-bs-theme-value="${theme}"]`);

        if (!themeSwitcherText || !activeThemeIcon || !btnToActive) {
            return;
        }

        const svgOfActiveBtn = btnToActive.querySelector("svg use")?.getAttribute("href");

        document.querySelectorAll<HTMLElement>("[data-bs-theme-value]").forEach(element => {
            element.classList.remove("active");
            element.setAttribute("aria-pressed", "false");
        });

        btnToActive.classList.add("active");
        btnToActive.setAttribute("aria-pressed", "true");
        if (svgOfActiveBtn) {
            activeThemeIcon.setAttribute("href", svgOfActiveBtn);
        }
        const themeSwitcherLabel = `${themeSwitcherText.textContent} (${btnToActive.dataset.bsThemeValue})`;
        themeSwitcher.setAttribute("aria-label", themeSwitcherLabel);

        if (focus) {
            themeSwitcher.focus();
        }
    };

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        const storedTheme = getStoredTheme();
        if (storedTheme !== "light" && storedTheme !== "dark") {
            setTheme(getPreferredTheme());
        }
    });

    window.addEventListener("DOMContentLoaded", () => {
        showActiveTheme(getPreferredTheme());

        document.querySelectorAll<HTMLElement>("[data-bs-theme-value]").forEach(toggle => {
            toggle.addEventListener("click", () => {
                const theme = toggle.getAttribute("data-bs-theme-value");
                if (!theme || !isTheme(theme)) {
                    return;
                }
                setStoredTheme(theme);
                setTheme(theme);
                showActiveTheme(theme, true);
            });
        });
    });
})();
