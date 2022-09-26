import { test, expect } from "@jest/globals";
import { ElementHandle } from "puppeteer";
import { assert, assertDefined } from "../../src/utils";

import { pageHandler } from "../utils/page";

const content = `
*,
*::after,
*::before {
    transition-delay: 0s !important;
    transition-duration: 0s !important;
}`;

test(
    "contact-modal-opens",
    pageHandler("/contributor/evaluation/PK/edit/normal.html", async page => {
        await page.addStyleTag({ content });

        const modalVisible = async (modalHandle: ElementHandle) =>
            await page.evaluate(modal => {
                return window.getComputedStyle(modal).display === "block";
            }, modalHandle);

        // "Request changes" button

        const changeEvaluationRequestModal = await page.$("#changeEvaluationRequestModal");
        assertDefined(changeEvaluationRequestModal);
        expect(await modalVisible(changeEvaluationRequestModal)).toBe(false);

        const [requestChangesButton] = await page.$x("//button[contains(., 'Request changes')]");
        assertDefined(requestChangesButton);
        await (requestChangesButton as ElementHandle<Element>).click();
        await page.waitForSelector("#changeEvaluationRequestModal", { visible: true });
        expect(await modalVisible(changeEvaluationRequestModal)).toBe(true);

        // wait for open and close again
        await page.waitForSelector("textarea:focus", { visible: true });
        await changeEvaluationRequestModal.press("Escape");
        await page.waitForSelector("#changeEvaluationRequestModal", { hidden: true });

        // "Request creation of new account" button

        const createAccountRequestModal = await page.$("#createAccountRequestModal");
        assertDefined(createAccountRequestModal);
        expect(await modalVisible(createAccountRequestModal)).toBe(false);

        const [requestAccountCreateButton] = await page.$x("//button[contains(., 'Request creation of new account')]");
        assertDefined(requestAccountCreateButton);
        await (requestAccountCreateButton as ElementHandle<Element>).click();
        await page.waitForSelector("#createAccountRequestModal", { visible: true });
        expect(await modalVisible(createAccountRequestModal)).toBe(true);
    }),
);

test(
    "contact-modal-opens-with-allow-editors-to-edit",
    pageHandler("/contributor/evaluation/PK/edit/allow_editors_to_edit.html", async page => {
        await page.addStyleTag({ content });

        const modalVisible = async (modalHandle: ElementHandle) =>
            await page.evaluate(modal => {
                return window.getComputedStyle(modal).display === "block";
            }, modalHandle);

        const createAccountRequestModal = await page.$("#createAccountRequestModal");
        assertDefined(createAccountRequestModal);
        expect(await modalVisible(createAccountRequestModal)).toBe(false);

        const [button1, button2] = await page.$x("//button[contains(., 'Request creation of new account')]");
        assertDefined(button1);
        assertDefined(button2);

        await (button1 as ElementHandle<Element>).click();
        await page.waitForSelector("#createAccountRequestModal", { visible: true });
        expect(await modalVisible(createAccountRequestModal)).toBe(true);

        // wait for open and close again
        await page.waitForSelector("textarea:focus", { visible: true });
        await createAccountRequestModal.press("Escape");
        await page.waitForSelector("createAccountRequestModal", { hidden: true });

        await (button2 as ElementHandle<Element>).click();
        await page.waitForSelector("#createAccountRequestModal", { visible: true });
        expect(await modalVisible(createAccountRequestModal)).toBe(true);
    }),
);
