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
export const CSRF_HEADERS = { "X-CSRFToken": csrftoken };

(globalThis as any).CSRF_HEADERS = CSRF_HEADERS;

export const testable = {
    getCookie,
};
