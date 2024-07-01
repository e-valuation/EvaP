import { selectOrError } from "./utils.js";

const OPEN_CLOSE_TIMEOUT = 2000;

export class InfoboxLogic {
    private readonly infobox: HTMLDivElement;
    private readonly closeButton: HTMLButtonElement;
    private readonly storageKey: string;
    private timeout?: number;

    constructor(infobox_id: string) {
        this.infobox = selectOrError("#infobox-" + infobox_id);
        this.closeButton = selectOrError(".callout-infobox-close", this.infobox);
        this.storageKey = "infobox-" + infobox_id;
    }

    public attach = (): void => {
        // close the infobox and save state
        this.closeButton.addEventListener("click", event => {
            this.infobox.classList.add("closing");
            this.infobox.classList.remove("opening");
            clearTimeout(this.timeout);
            setTimeout(() => {
                this.infobox.classList.replace("closing", "closed");
            }, OPEN_CLOSE_TIMEOUT);
            event.stopPropagation(); // prevent immediate reopening: close button is in header, which is the open button
            localStorage[this.storageKey] = "hide";
        });

        // open the infobox and save state
        this.infobox.addEventListener("click", _ => {
            if (this.infobox.className.includes("closed")) {
                this.infobox.classList.replace("closed", "opening");
                this.timeout = setTimeout(() => {
                    this.infobox.classList.remove("opening");
                }, OPEN_CLOSE_TIMEOUT);
                localStorage[this.storageKey] = "show";
            }
        });
    };
}
