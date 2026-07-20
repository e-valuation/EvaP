/*!
 * Adapted color mode toggler from Bootstrap's docs (https://getbootstrap.com/)
 */

import { unwrap } from "./utils.js";

(() => {
    "use strict";

    const storedTheme = localStorage.getItem("theme");

    const getPreferredTheme = () => {
        if (storedTheme) {
            return storedTheme;
        }

        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    };

    const setTheme = function (theme: string) {
        document.documentElement.setAttribute("data-bs-theme", theme);
    };

    setTheme(getPreferredTheme());

    const showActiveTheme = (theme: string) => {
        const btnToActive = unwrap(document.querySelector(`[data-bs-theme-value="${theme}"]`));

        document.querySelectorAll("[data-bs-theme-value]").forEach(element => {
            element.classList.remove("active");
        });

        btnToActive.classList.add("active");
    };

    window.addEventListener("DOMContentLoaded", () => {
        showActiveTheme(getPreferredTheme());

        document.querySelectorAll("[data-bs-theme-value]").forEach(toggle => {
            toggle.addEventListener("click", () => {
                const theme = unwrap(toggle.getAttribute("data-bs-theme-value"));
                localStorage.setItem("theme", theme);
                setTheme(theme);
                showActiveTheme(theme);
            });
        });
    });
})();
