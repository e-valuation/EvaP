declare const bootstrap: typeof import("bootstrap");

import { selectOrError, sleep, assert } from "./utils.js";
import { csrfHeader } from "./csrf-utils.js";

const success_message_timeout = 3000;

export class ContactModalLogic {
    private readonly modal: bootstrap.Modal;
    private readonly successMessageModal: bootstrap.Modal;
    private readonly actionButtonElement: HTMLButtonElement;
    private readonly messageTextElement: HTMLInputElement;
    private readonly anonymousRadioElement: HTMLInputElement;
    private readonly modalId: string;
    private readonly title: string;

    constructor(modalId: string, title: string) {
        this.modalId = modalId;
        this.title = title;
        this.modal = new bootstrap.Modal(selectOrError("#" + modalId));
        this.successMessageModal = new bootstrap.Modal(selectOrError("#successMessageModal_" + modalId));
        this.actionButtonElement = selectOrError("#" + modalId + "ActionButton");
        this.messageTextElement = selectOrError("#" + modalId + "MessageText");
        this.anonymousRadioElement = selectOrError("#" + modalId + "AnonymName");
        this.actionButtonElement.addEventListener("click", async event => {
            this.actionButtonElement.disabled = true;
            event.preventDefault();
            const message = this.messageTextElement.value;
            if (message.trim() == "") {
                this.modal.hide();
                this.actionButtonElement.disabled = false;
                return;
            }
            try {
                let response = await fetch("/contact", {
                    body: new URLSearchParams({
                        anonymous: String(this.anonymousRadioElement.checked),
                        message,
                        title: this.title,
                    }),
                    headers: csrfHeader,
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

            await sleep(success_message_timeout);
            this.successMessageModal.hide();
            this.actionButtonElement.disabled = false;
        });
        selectOrError("#" + modalId + "ShowButton").addEventListener("click", () => {
            this.modal.show();
        });
    }
}
