// based on: https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
function getCookie(name: string): string | null {
    if (document.cookie !== "") {
        const cookie = document.cookie
            .split(";")
            .map(cookie => cookie.trim())
            .find(cookie => cookie.substring(0, name.length + 1) === `${name}=`);
        if (cookie) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}
const csrftoken = getCookie("csrftoken")!;

function doesMethodRequireCsrfToken(method: string): boolean {
    // these HTTP methods do not require CSRF protection
    return ["POST", "PUT", "DELETE", "PATCH"].includes(method.toUpperCase());
}

function isUrlCrossDomain(url: string): boolean {
    return new URL(document.baseURI).origin !== new URL(url, document.baseURI).origin;
}

// setup ajax sending csrf token
$.ajaxSetup({
    beforeSend: function (xhr: JQuery.jqXHR, settings: JQuery.AjaxSettings) {
        const methodRequiresCsrfToken = settings.type && doesMethodRequireCsrfToken(settings.type);
        if (methodRequiresCsrfToken && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    },
});

// Add CSRF token to regular forms on submit.
// This reduces boilerplate code in the templates and makes the form's HTML cacheable.
for (const form of document.forms) {
    form.addEventListener("submit", (ev: Event) => {
        // in case a form gets submitted twice
        if (form.querySelectorAll("input[name=csrfmiddlewaretoken]").length > 0) {
            return;
        }

        const { submitter } = ev as SubmitEvent;
        const action = submitter?.getAttribute("formaction") ?? form.getAttribute("action");
        const method = submitter?.getAttribute("formmethod") ?? form.getAttribute("method");

        if (method && doesMethodRequireCsrfToken(method) && action && !isUrlCrossDomain(action)) {
            const inputElement = document.createElement("input");
            inputElement.setAttribute("type", "hidden");
            inputElement.setAttribute("name", "csrfmiddlewaretoken");
            inputElement.setAttribute("value", csrftoken);

            form.insertAdjacentElement("afterbegin", inputElement);
        }
    });
}

export const testable = {
    getCookie,
    doesMethodRequireCsrfToken,
};
