import { getCookie } from "./utils";

const csrftoken = getCookie("csrftoken")!;
export const CSRF_HEADERS = { "X-CSRFToken": csrftoken };

function isMethodCsrfSafe(method: string): boolean {
    // these HTTP methods do not require CSRF protection
    return ["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
}

// setup ajax sending csrf token
$.ajaxSetup({
    beforeSend: function (xhr: JQuery.jqXHR, settings: JQuery.AjaxSettings) {
        const isMethodSafe = settings.method && isMethodCsrfSafe(settings.method);
        if (!isMethodSafe && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    },
});

export const testable = {
    isMethodCsrfSafe,
};
