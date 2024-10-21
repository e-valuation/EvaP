declare const bootstrap: typeof import("bootstrap");

import { selectOrError, sleep, assert } from "./utils.js";
import { CSRF_HEADERS } from "./csrf-utils.js";

const SUCCESS_MESSAGE_TIMEOUT = 3000;

export class ContactModalLogic {
    private readonly modal: bootstrap.Modal;
    private readonly successMessageModal: bootstrap.Modal;
    private readonly actionButtonElement: HTMLButtonElement;
    private readonly messageTextElement: HTMLInputElement;
    private readonly showButtonElements: HTMLElement[];
    private readonly title: string;

    // may be null if anonymous feedback is not enabled
    private readonly anonymousRadioElement: HTMLInputElement | null;

    constructor(modalId: string, title: string) {
        this.title = title;
        this.modal = new bootstrap.Modal(selectOrError("#" + modalId));
        this.successMessageModal = new bootstrap.Modal(selectOrError("#successMessageModal_" + modalId));
        this.actionButtonElement = selectOrError("#" + modalId + "ActionButton");
        this.messageTextElement = selectOrError("#" + modalId + "MessageText");
        this.anonymousRadioElement = document.querySelector<HTMLInputElement>("#" + modalId + "AnonymousName");
        this.showButtonElements = Array.from(document.querySelectorAll(`#${modalId}ShowButton, .${modalId}ShowButton`));
    }

    public attach = (): void => {
        this.actionButtonElement.addEventListener("click", async event => {
            this.actionButtonElement.disabled = true;
            event.preventDefault();
            const message = this.messageTextElement.value;
            if (message.trim() === "") {
                this.modal.hide();
                this.actionButtonElement.disabled = false;
                return;
            }
            try {
                const response = await fetch("/contact", {
                    body: new URLSearchParams({
                        anonymous: String(this.anonymousRadioElement !== null && this.anonymousRadioElement.checked),
                        message,
                        title: this.title,
                    }),
                    headers: CSRF_HEADERS,
                    method: "POST",
                });
                assert(response.ok);
            } catch (_) {
                window.alert("Sending failed, sorry!");
                return;
            }
            this.modal.hide();
            this.successMessageModal.show();
            this.messageTextElement.value = "";

            await sleep(SUCCESS_MESSAGE_TIMEOUT);
            this.successMessageModal.hide();
            this.actionButtonElement.disabled = false;
        });

        this.showButtonElements.forEach(button =>
            button.addEventListener("click", () => {
                this.modal.show();
            }),
        );
    };
}
