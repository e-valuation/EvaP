declare const bootstrap: typeof import("bootstrap");

import { selectOrError } from "./utils.js";

const OPEN_CLOSE_TIMEOUT = 2000;

export class InfoboxLogic {
    private readonly infobox: HTMLDivElement;
    private readonly closeButton: HTMLButtonElement;
    private readonly storageKey: string;

    constructor(infobox_id: string) {
        this.infobox = selectOrError("#" + infobox_id);
        this.closeButton = selectOrError("#" + infobox_id + " .callout-closable-close");
        this.storageKey = "infobox_" + infobox_id;

        // set infobox to hidden, if user closed it before
        if (localStorage[this.storageKey] === "hide") this.infobox.classList.add("closed");
    }

    public attach = (): void => {
        // close the infobox and save state
        this.closeButton.addEventListener("click", async event => {
            this.infobox.classList.add("closing");
            setTimeout(() => {
                this.infobox.classList.replace("closing", "closed");
            }, OPEN_CLOSE_TIMEOUT);
            event.stopPropagation();
            localStorage[this.storageKey] = "hide";
        });

        // open the infobox and save state
        this.infobox.addEventListener("click", async event => {
            if (this.infobox.className.includes("closed")) {
                this.infobox.classList.replace("closed", "opening");
                setTimeout(() => {
                    this.infobox.classList.replace("opening", "opened");
                }, OPEN_CLOSE_TIMEOUT);
                localStorage[this.storageKey] = "show";
            }
        });
    };
}
