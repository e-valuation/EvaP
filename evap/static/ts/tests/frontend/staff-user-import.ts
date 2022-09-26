import { test, expect } from "@jest/globals";

import { pageHandler } from "../utils/page";

test(
    "copies header",
    pageHandler("staff/user/import/normal.html", async page => {
        await page.click(".btn-link");
        const copiedText = await page.evaluate(() => {
            return navigator.clipboard.readText();
        });
        expect(copiedText).toBe("Title\tFirst name\tLast name\tEmail");
    }),
);
