import { assert, selectOrError } from "./utils.js";

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

const showActiveTheme = (theme: Theme): void => {
    const btnToActive = selectOrError<HTMLElement>(`[data-bs-theme-value="${theme}"]`);

    document.querySelectorAll<HTMLElement>("[data-bs-theme-value]").forEach(element => {
        element.classList.remove("active");
        element.setAttribute("aria-pressed", "false");
    });

    btnToActive.classList.add("active");
    btnToActive.setAttribute("aria-pressed", "true");
};

setTheme(getPreferredTheme());

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
            const theme = toggle.getAttribute("data-bs-theme-value")!;
            assert(isTheme(theme));

            setStoredTheme(theme);
            setTheme(theme);
            showActiveTheme(theme);
        });
    });
});
