export const selectOrError = <T extends Element>(selector: string, root: Element | Document = document): T => {
    const elem = root.querySelector<T>(selector);
    assert(elem, `Element with selector ${selector} not found`);
    return elem;
};

export function assert(condition: unknown, message: string = "Assertion Failed"): asserts condition {
    if (!condition) throw new Error(message);
}

export function assertDefined<T>(val: T): asserts val is NonNullable<T> {
    assert(val !== undefined);
    assert(val !== null);
}

export const sleep = (ms?: number): Promise<number> => {
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

export function setCookie(key: string, value: string): void {
    document.cookie = key + "=" + value;
}

export const testable = {
    getCookie,
};
export const clamp = (val: number, lowest: number, highest: number) => Math.min(highest, Math.max(lowest, val));

export const saneParseInt = (s: string): number | null => {
    if (!/^-?[0-9]+$/.test(s)) {
        return null;
    }
    const num = parseInt(s);
    assert(!isNaN(num));
    return num;
};

export const findPreviousElementSibling = (element: Element, selector: string): Element | null => {
    while (element.previousElementSibling) {
        element = element.previousElementSibling;
        if (element.matches(selector)) {
            return element;
        }
    }
    return null;
};

export const isVisible = (element: HTMLElement): boolean => element.offsetWidth !== 0 || element.offsetHeight !== 0;
