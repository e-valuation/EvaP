type Theme = "light" | "dark" | "auto";
type Colors = "default" | "alternative";

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
const isTheme = (value: string | null): value is Theme => value === "light" || value === "dark" || value === "auto";
const isColors = (value: string | null): value is Colors => value === "default" || value === "alternative";

const showActiveOption = (attribute: string, value: string): void => {
    document.querySelectorAll<HTMLElement>(`[${attribute}]`).forEach(button => {
        const active = button.getAttribute(attribute) === value;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
    });
};

const getStoredTheme = (): Theme | null => {
    const item = localStorage.getItem("theme");
    return isTheme(item) ? item : null;
};
const getPreferredTheme = (): Theme => getStoredTheme() ?? (systemTheme.matches ? "dark" : "light");

const setTheme = (theme: Theme): void => {
    const resolvedTheme = theme === "auto" ? (systemTheme.matches ? "dark" : "light") : theme;
    document.documentElement.setAttribute("data-bs-theme", resolvedTheme);
    showActiveOption("data-bs-theme-value", theme);
};

const getPreferredColors = (): Colors => {
    const storedColors = localStorage.getItem("evap-colors");
    return isColors(storedColors) ? storedColors : "default";
};

const setColors = (colors: Colors): void => {
    document.querySelectorAll<HTMLLinkElement>("#evap-default-colors, #evap-alternative-colors").forEach(sheet => {
        sheet.media = sheet.id === `evap-${colors}-colors` ? "all" : "not all";
    });
    showActiveOption("data-evap-colors-value", colors);
};

const applyPreferences = (): void => {
    setTheme(getPreferredTheme());
    setColors(getPreferredColors());
};

applyPreferences();

systemTheme.addEventListener("change", () => {
    const storedTheme = getStoredTheme();
    if (storedTheme !== "light" && storedTheme !== "dark") {
        setTheme(getPreferredTheme());
    }
});

window.addEventListener("DOMContentLoaded", () => {
    applyPreferences();

    document.querySelectorAll<HTMLElement>("[data-evap-colors-value]").forEach(toggle => {
        toggle.addEventListener("click", () => {
            const colors = toggle.getAttribute("data-evap-colors-value");
            if (!isColors(colors)) {
                return;
            }
            localStorage.setItem("evap-colors", colors);
            setColors(colors);
        });
    });

    document.querySelectorAll<HTMLElement>("[data-bs-theme-value]").forEach(toggle => {
        toggle.addEventListener("click", () => {
            const theme = toggle.getAttribute("data-bs-theme-value") as Theme;
            localStorage.setItem("theme", theme);
            setTheme(theme);
            document.querySelector<HTMLElement>("#navBarColorModeDropdownMenuLink")?.focus();
        });
    });
});
