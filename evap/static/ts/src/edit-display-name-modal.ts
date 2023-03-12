declare const bootstrap: typeof import("bootstrap");

import { selectOrError, sleep, assert } from "./utils.js";
import { CSRF_HEADERS } from "./csrf-utils.js";

const SUCCESS_MESSAGE_TIMEOUT = 3000;

export class EditDisplayNameModal {
    private readonly modal: bootstrap.Modal;
    private readonly successMessageModal: bootstrap.Modal;
    private readonly actionButtonElement: HTMLButtonElement;
    private readonly showButtonElements: Array<HTMLElement>;
    private readonly email: string;
    private displayNameTextElement: HTMLInputElement;

    // may be null if anonymous feedback is not enabled
    private readonly anonymousRadioElement: HTMLInputElement | null;

    constructor(modalId: string, email: string) {
        this.email = email;
        this.displayNameTextElement = selectOrError("#" + modalId + "DisplayName");
        this.modal = new bootstrap.Modal(selectOrError("#" + modalId));
        this.successMessageModal = new bootstrap.Modal(selectOrError("#successMessageModal_" + modalId));
        this.actionButtonElement = selectOrError("#" + modalId + "ActionButton");
        this.anonymousRadioElement = document.querySelector<HTMLInputElement>("#" + modalId + "AnonymousName");
        this.showButtonElements = Array.from(document.querySelectorAll(`#${modalId}ShowButton, .${modalId}ShowButton`));
    }

    public attach = (): void => {
        this.actionButtonElement.addEventListener("click", async event => {
            this.actionButtonElement.disabled = true;
            event.preventDefault();
            const displayName = this.displayNameTextElement.value;
            if (displayName.trim() === "") {
                this.modal.hide();
                this.actionButtonElement.disabled = false;
                return;
            }
            try {
                const response = await fetch("/display_name", {
                    body: new URLSearchParams({
                        email: this.email,
                        displayName: displayName,
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
