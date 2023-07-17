/**
 * @jest-environment jsdom
 */

Object.defineProperty(document, "cookie", {
    get: () =>
        `foo=${encodeURIComponent("F00")}; ` +
        `csrftoken=${encodeURIComponent("token")}; ` +
        `bar=${encodeURIComponent("+{)")}; ` +
        `baz=${encodeURIComponent("+{`")}`,
});

// @ts-ignore
window.$ = require("../../../js/jquery-2.1.3.min");

import { testable } from "src/csrf-utils";

const { getCookie, isMethodCsrfSafe } = testable;

test("parse cookie", () => {
    expect(getCookie("foo")).toBe("F00");
    expect(getCookie("bar")).toBe("+{)");
    expect(getCookie("baz")).toBe("+{`");
    expect(getCookie("csrftoken")).toBe("token");
    expect(getCookie("qux")).toBe(null);
});

test.each(["GET", "HEAD", "OPTIONS", "TRACE"])("method %s is considered safe", method => {
    expect(isMethodCsrfSafe(method)).toBe(true);
});

test.each(["POST", "PUT", "DELETE"])("method %s is considered unsafe", method => {
    expect(isMethodCsrfSafe(method)).toBe(false);
});

test("send csrf token in request", () => {
    const mock = {
        open: jest.fn(),
        send: jest.fn(),
        setRequestHeader: jest.fn(),
    };
    window.XMLHttpRequest = jest.fn(() => mock) as unknown as typeof window.XMLHttpRequest;

    $.post("/receiver");

    expect(mock.setRequestHeader).toBeCalledWith("X-CSRFToken", "token");
});
