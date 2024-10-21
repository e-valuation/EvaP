import { Page } from "puppeteer";

import { pageHandler } from "../utils/page";
import "../utils/matchers";

async function fetchVisibleRows(page: Page): Promise<string[][]> {
    return await page.$$eval(".heading-row", rows => {
        return rows.map(row => {
            const evaluationName = row.querySelector(".evaluation-name")!.textContent!.trim();
            const semester = row.querySelector(".semester-short-name")!.textContent!.trim();
            return [evaluationName, semester];
        });
    });
}

test(
    "initially sort by evaluation and semester",
    pageHandler("results/student.html", async page => {
        expect(await fetchVisibleRows(page)).toEqual([
            ["Course A", "ST 14"],
            ["Course A", "WT 13/14"],
            ["Course A", "ST 13"],
            ["Course C", "ST 14"],
            ["Course D", "ST 14"],
            ["Course E", "ST 13"],
        ]);
    }),
);

test(
    "filter with search input",
    pageHandler("results/student.html", async page => {
        await page.type("input[name=search]", "Exam");
        await new Promise(resolve => setTimeout(resolve, 200)); // wait for input to debounce

        expect(await fetchVisibleRows(page)).toEqual([["Course A", "ST 13"]]);
    }),
);

test(
    "filter with program checkbox",
    pageHandler("results/student.html", async page => {
        await page.click("input[name=program][data-filter='Bachelor A']");

        expect(await fetchVisibleRows(page)).toEqual([
            ["Course A", "ST 14"],
            ["Course A", "WT 13/14"],
            ["Course A", "ST 13"],
            ["Course C", "ST 14"],
        ]);
    }),
);

test(
    "filter with course type checkbox",
    pageHandler("results/student.html", async page => {
        await page.click("input[name=courseType][data-filter=Seminar]");

        expect(await fetchVisibleRows(page)).toEqual([
            ["Course C", "ST 14"],
            ["Course E", "ST 13"],
        ]);
    }),
);

test(
    "filter with semester checkbox",
    pageHandler("results/student.html", async page => {
        await page.click("input[name=semester][data-filter='ST 13']");

        expect(await fetchVisibleRows(page)).toEqual([
            ["Course A", "ST 13"],
            ["Course E", "ST 13"],
        ]);
    }),
);

test(
    "clear filters",
    pageHandler("results/student.html", async page => {
        const searchInput = (await page.$("input[name=search]"))!;
        const programCheckbox = (await page.$("input[name=program][data-filter='Bachelor A']"))!;
        const courseTypeCheckbox = (await page.$("input[name=courseType][data-filter=Lecture]"))!;
        const semesterCheckbox = (await page.$("input[name=semester][data-filter='ST 14']"))!;

        await searchInput.type("Some search text");
        await programCheckbox.click();
        await courseTypeCheckbox.click();
        await semesterCheckbox.click();

        await page.click("[data-reset=filter]");

        expect(await searchInput.evaluate(searchInput => searchInput.value)).toBe("");
        await expect(programCheckbox).not.toBeChecked();
        await expect(courseTypeCheckbox).not.toBeChecked();
        await expect(semesterCheckbox).not.toBeChecked();
    }),
);
