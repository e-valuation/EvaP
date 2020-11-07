import * as fs from "fs";
import * as path from "path";
import { Browser, Page } from "puppeteer";
import { DoneFn } from "@jest/types/build/Global";

const contentTypeByExtension: Map<string, string> = new Map([
    [".css", "text/css"],
    [".js", "application/javascript"],
    [".png", "image/png"],
    [".svg", "image/svg+xml"],
]);

async function createPage(browser: Browser): Promise<Page> {
    const staticPrefix = "/static/";

    const page = await browser.newPage();
    await page.setRequestInterception(true);
    page.on("request", request => {
        const extension = path.extname(request.url());
        const pathname = new URL(request.url()).pathname;
        if (extension === ".html") {
            request.continue();
        } else if (pathname.startsWith(staticPrefix)) {
            const asset = pathname.substr(staticPrefix.length);
            const body = fs.readFileSync(path.join(__dirname, "..", "..", "..", asset));
            request.respond({
                contentType: contentTypeByExtension.get(extension),
                body,
            });
        } else {
            request.abort();
        }
    });
    return page;
}

export function pageHandler(fileName: string, fn: (page: Page) => void): (done?: DoneFn) => void {
    return async done => {
        let finished = false;
        // This wrapper ensures that done() is only called once
        async function finish(reason?: Error) {
            if (!finished) {
                finished = true;
                await page.evaluate(() => {
                    localStorage.clear();
                });
                done!(reason);
            }
        }

        const context = await browser.defaultBrowserContext();
        await context.overridePermissions("file:", ["clipboard-read"]);


        const page = await createPage(browser);
        page.on("pageerror", async error => {
            await finish(new Error(error.message));
        });

        const filePath = path.join(__dirname, "..", "..", "rendered", fileName);
        await page.goto(`file:${filePath}`, {waitUntil: "networkidle0"});

        try {
            await fn(page);
            await finish();
        } catch (error) {
            await finish(error);
        }
    };
}
