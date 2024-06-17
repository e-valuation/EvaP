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

import { testable } from "src/csrf-utils";

const { getCookie } = testable;

test("parse cookie", () => {
    expect(getCookie("foo")).toBe("F00");
    expect(getCookie("bar")).toBe("+{)");
    expect(getCookie("baz")).toBe("+{`");
    expect(getCookie("csrftoken")).toBe("token");
    expect(getCookie("qux")).toBe(null);
});
