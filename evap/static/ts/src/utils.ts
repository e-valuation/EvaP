export const selectOrError = <T extends Element>(selectors: string): T => {
    const elem = document.querySelector<T>(selectors);
    assert(elem, `Element with id ${selectors} not found`);
    return elem;
};

export function assert(condition: unknown, message: string = "Assertion Failed"): asserts condition {
    if (!condition) throw new Error(message);
}

export const sleep = (ms: number): Promise<number> => {
    return new Promise(resolve => window.setTimeout(resolve, ms));
};

// based on: https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
export function getCookie(name: string): string | null {
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

export function setCookie(key: string, value: string) {
    document.cookie = key + "=" + value;
}

export const testable = {
    getCookie,
    isMethodCsrfSafe,
};
