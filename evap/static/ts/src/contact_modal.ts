declare const csrf: typeof import("./csrf-utils");
declare const bootstrap: typeof import("bootstrap");

class ContactModalLogic {
    private readonly modal: bootstrap.Modal;
    private readonly successMessageModal: bootstrap.Modal;
    private readonly actionButtonElement: HTMLButtonElement;
    private readonly messageTextElement: HTMLInputElement;
    private readonly modal_id: string;
    private readonly title: string;

    constructor(modal_id: string, title: string) {
        this.modal_id = modal_id;
        this.title = title;
        this.modal = new bootstrap.Modal(<HTMLElement>document.getElementById(modal_id));
        this.successMessageModal = new bootstrap.Modal(
            <HTMLElement>document.getElementById("successMessageModal_" + modal_id),
        );
        this.actionButtonElement = document.getElementById(this.modal_id + "ActionButton") as HTMLButtonElement;
        this.messageTextElement = document.getElementById(this.modal_id + "MessageText") as HTMLInputElement;
        this.actionButtonElement.addEventListener("click", event => {
            this.ModalAction(event);
        });
    }

    public ModalShow() {
        this.modal.show();
    }

    public ModalAction(event: MouseEvent) {
        this.actionButtonElement.disabled = true;
        event.preventDefault();
        let message = this.messageTextElement.value;
        let anonymous = (<HTMLInputElement>document.getElementById(this.modal_id + "AnonymName")).value;
        if (message.trim() == "") {
            this.modal.hide();
            this.actionButtonElement.disabled = false;
            return;
        }

        const res_promise = fetch("/contact", {
            method: "POST",
            headers: csrf.csrfheader,
            body: JSON.stringify({ message: message, title: this.title, anonymous: anonymous }),
        });

        res_promise.then(res => {
            if (!res.ok) {
                window.alert("Sending failed, sorry!");
                return;
            }
            this.modal.hide();
            this.successMessageModal.show();

            this.messageTextElement.value = "";
            setTimeout(() => {
                this.successMessageModal.hide();
                this.actionButtonElement.disabled = false;
            }, 3000);
        });
        res_promise.catch(_ => window.alert("Sending failed, sorry!"));
    }
}
