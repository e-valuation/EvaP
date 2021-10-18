// based on: https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
function getCookie(name: string): string | null {
    if (document.cookie !== "") {
        const cookie = document.cookie.split(";")
            .map(cookie => cookie.trim())
            .find(cookie => cookie.substring(0, name.length + 1) === `${name}=`);
        if (cookie) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}
const csrftoken = getCookie("csrftoken")!;

function isMethodCsrfSafe(method: string): boolean {
    // these HTTP methods do not require CSRF protection
    return ["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
}

// setup ajax sending csrf token
$.ajaxSetup({
    beforeSend: function(xhr: JQuery.jqXHR, settings: JQuery.AjaxSettings) {
        const isMethodSafe = settings.method && isMethodCsrfSafe(settings.method);
        if (!isMethodSafe && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    },
});

export const testable = {
    getCookie,
    isMethodCsrfSafe,
};
