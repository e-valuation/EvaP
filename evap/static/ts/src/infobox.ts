declare const bootstrap: typeof import("bootstrap");

import { selectOrError } from "./utils.js";

const OPEN_CLOSE_TIMEOUT = 2000;

export class InfoboxLogic {
    private readonly infobox: HTMLDivElement;
    private readonly closeButton: HTMLButtonElement;
    private readonly storageKey: string;

    constructor(infobox_id: string) {
        this.infobox = selectOrError("#" + infobox_id);
        this.closeButton = selectOrError("#" + infobox_id + " .callout-infobox-close");
        this.storageKey = "infobox_" + infobox_id;
    }

    public attach = (): void => {
        // close the infobox and save state
        this.closeButton.addEventListener("click", async event => {
            this.infobox.classList.add("closing");
            setTimeout(() => {
                this.infobox.classList.replace("closing", "closed");
            }, OPEN_CLOSE_TIMEOUT);
            event.stopPropagation(); // prevent immediate reopening: close button is in header, which is the open button
            localStorage[this.storageKey] = "hide";
        });

        // open the infobox and save state
        this.infobox.addEventListener("click", async _ => {
            if (this.infobox.className.includes("closed")) {
                this.infobox.classList.replace("closed", "opening");
                setTimeout(() => {
                    this.infobox.classList.remove("opening");
                }, OPEN_CLOSE_TIMEOUT);
                localStorage[this.storageKey] = "show";
            }
        });
    };
}
