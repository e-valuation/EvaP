import { selectOrError } from "./utils.js";

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
            if (!this.infobox.className.includes("closed")) {
                this.infobox.classList.add("closed");
                event.stopPropagation(); // prevent immediate reopening: close button is part of the header, which is used as the open button
                localStorage[this.storageKey] = "hide";
            }
        });

        // open the infobox and save state
        this.infobox.addEventListener("click", async _ => {
            if (this.infobox.className.includes("closed")) {
                this.infobox.classList.remove("closed");
                localStorage[this.storageKey] = "show";
            }
        });
    };
}
