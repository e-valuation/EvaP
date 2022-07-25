import { test, expect } from "@jest/globals";

import { pageHandler } from "../utils/page";

interface TomSelectedHtmlSelectElement extends HTMLSelectElement {
    tomselect: any;
}

test("copies header", pageHandler(
    "/staff/semester/PK/evaluation/PK/edit/normal.html",
    async page => {
        const managerId = await page.evaluate(() => {
            const tomselect = (document.getElementById("id_contributions-0-contributor") as TomSelectedHtmlSelectElement).tomselect;
            const options = tomselect!.options;
            const managerOption = Object.keys(options).find(key => options[key].text == "manager (manager)");
            tomselect.setValue(managerOption);
            return managerOption;
        });
        console.log("managerID: " + managerId);

        const editorLabels = await page.$x("//label[contains(text(), 'Editor')]");
        const ownAndGeneralLabels = await page.$x("//label[contains(text(), 'Own and general')]");
        if (editorLabels.length < 1 || ownAndGeneralLabels.length < 1) {
          throw new Error("Button group buttons not found.");
        }

        await (editorLabels[0] as any).click();
        await (ownAndGeneralLabels[0] as any).click();

        const formData = await page.evaluate(() => {
            return new FormData(document.getElementById("evaluation-form") as HTMLFormElement);
        });

        console.log(formData);

        expect(formData.get("contributions-0-contributor")).toBe(managerId);
        // expect(formData.get("contributions-0-order")).toBe("0");
        // expect(formData.get("contributions-0-role")).toBe("");
        // expect(formData.get("contributions-0-textanswer_visibility")).toBe("OWN");
    },
));
