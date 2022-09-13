/**
 * @jest-environment jsdom
 */

import { testable } from "ts/src/csrf-utils";

const { isMethodCsrfSafe } = testable;

test.each([
    "GET",
    "HEAD",
    "OPTIONS",
    "TRACE",
])("method %s is considered safe", method => {
    expect(isMethodCsrfSafe(method)).toBe(true);
});

test.each([
    "POST",
    "PUT",
    "DELETE",
])("method %s is considered unsafe", method => {
    expect(isMethodCsrfSafe(method)).toBe(false);
})

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
