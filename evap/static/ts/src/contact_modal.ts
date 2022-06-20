import { sleep } from "./utils";

declare const csrfUtils: typeof import("./csrf-utils");
declare const bootstrap: typeof import("bootstrap");
declare const utils: typeof import("src/utils");

const timeout = 3000;

class ContactModalLogic {
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
        this.modal = new bootstrap.Modal(utils.expectElementById(modalId));
        this.successMessageModal = new bootstrap.Modal(utils.expectElementById("successMessageModal_" + modalId));
        this.actionButtonElement = utils.expectElementById(modalId + "ActionButton");
        this.messageTextElement = utils.expectElementById(modalId + "MessageText");
        this.anonymousRadioElement = utils.expectElementById(modalId + "AnonymName");
        this.actionButtonElement.addEventListener("click", async event => {
            this.actionButtonElement.disabled = true;
            event.preventDefault();
            const message = this.messageTextElement.value;
            if (message.trim() == "") {
                this.modal.hide();
                this.actionButtonElement.disabled = false;
                return;
            }
            let response;
            try {
                response = await fetch("/contact", {
                    body: JSON.stringify({
                        message,
                        title: this.title,
                        anonymous: this.anonymousRadioElement.value,
                    }),
                    headers: csrfUtils.csrfHeader,
                    method: "POST",
                });
                utils.assert(response.ok);
            } catch (_) {
                window.alert("Sending failed, sorry!");
                return;
            }
            this.modal.hide();
            this.successMessageModal.show();
            this.messageTextElement.value = "";

            await sleep(timeout);
            this.successMessageModal.hide();
            this.actionButtonElement.disabled = false;
        });
    }

    public showModal(): void {
        this.modal.show();
    }
}
