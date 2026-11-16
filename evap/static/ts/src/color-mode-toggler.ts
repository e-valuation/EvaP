type Theme = "light" | "dark" | "auto";
type Colors = "default" | "alternative";

const getPreferredSystemTheme = (): Theme =>
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
const isTheme = (value: string | null): value is Theme => value === "light" || value === "dark" || value === "auto";
const isColors = (value: string | null): value is Colors => value === "default" || value === "alternative";

const getStoredTheme = (): Theme | null => {
    const item = localStorage.getItem("theme");
    return isTheme(item) ? item : null;
};
const getPreferredTheme = (): Theme => getStoredTheme() ?? getPreferredSystemTheme();

const setTheme = (theme: Theme): void => {
    const resolvedTheme = theme === "auto" ? getPreferredSystemTheme() : theme;
    document.documentElement.setAttribute("data-bs-theme", resolvedTheme);
};

const getPreferredColors = (): Colors => {
    const storedColors = localStorage.getItem("evap-colors");
    return isColors(storedColors) ? storedColors : "default";
};

const setColors = (colors: Colors): void => {
    document.querySelectorAll<HTMLLinkElement>("#evap-default-colors, #evap-alternative-colors").forEach(sheet => {
        sheet.media = sheet.id === `evap-${colors}-colors` ? "all" : "not all";
    });
};

setTheme(getPreferredTheme());
setColors(getPreferredColors());

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const storedTheme = getStoredTheme();
    if (storedTheme !== "light" && storedTheme !== "dark") {
        setTheme(getPreferredTheme());
    }
});

window.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll<HTMLInputElement>('input[name="evap-colors"]').forEach(toggle => {
        toggle.checked = toggle.value === getPreferredColors();
        toggle.addEventListener("change", () => {
            const colors = toggle.value as Colors;
            localStorage.setItem("evap-colors", colors);
            setColors(colors);
        });
    });

    document.querySelectorAll<HTMLInputElement>('input[name="theme"]').forEach(toggle => {
        toggle.checked = toggle.value === getPreferredTheme();
        toggle.addEventListener("change", () => {
            const theme = toggle.value as Theme;
            localStorage.setItem("theme", theme);
            setTheme(theme);
        });
    });
});
