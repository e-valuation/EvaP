import { test, expect } from "@jest/globals";
import { ElementHandle } from "puppeteer";

import { pageHandler } from "../utils/page";
import { assertDefined } from "../../src/utils";

// regression test for #1769
test(
    "changes form data",
    pageHandler("/staff/semester/PK/evaluation/PK/edit/normal.html", async page => {
        const managerId = await page.evaluate(() => {
            const tomselect = (document.getElementById("id_contributions-0-contributor") as any).tomselect;
            const options = tomselect.options;
            const managerOption = Object.keys(options).find(
                key => options[key].text == "manager (manager@institution.example.com)",
            );
            tomselect.setValue(managerOption);
            return managerOption;
        });
        assertDefined(managerId);

        const editorLabels = await page.$$("xpath/.//label[contains(text(), 'Editor')]");
        const ownAndGeneralLabels = await page.$$("xpath/.//label[contains(text(), 'Own and general')]");
        if (editorLabels.length < 1 || ownAndGeneralLabels.length < 1) {
            throw new Error("Button group buttons not found.");
        }

        await editorLabels[0].click();
        await ownAndGeneralLabels[0].click();

        const formData = await page.evaluate(() => {
            return Object.fromEntries(new FormData(document.getElementById("evaluation-form") as HTMLFormElement));
        });

        expect(formData["contributions-0-contributor"]).toBe(managerId);
        expect(formData["contributions-0-order"]).toBe("0");
        expect(formData["contributions-0-role"]).toBe("1");
        expect(formData["contributions-0-textanswer_visibility"]).toBe("GENERAL");
    }),
);
