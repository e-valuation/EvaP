import { selectOrError } from "./utils.js";

export class ConfirmationModal extends HTMLElement {
    static formAssociated = true;

    readonly dialog: HTMLDialogElement;
    readonly dialogForm: HTMLFormElement;
    readonly type: string;
    readonly internals: ElementInternals;

    constructor() {
        super();

        const template = selectOrError<HTMLTemplateElement>("#confirmation-modal-template").content;
        const shadowRoot = this.attachShadow({ mode: "open" });
        shadowRoot.appendChild(template.cloneNode(true));

        this.type = this.getAttribute("type") ?? "button";
        this.internals = this.attachInternals();

        this.dialog = selectOrError("dialog", shadowRoot);

        const confirmButton = selectOrError("[data-event-type=confirm]", this.dialog);
        const confirmButtonExtraClass = this.getAttribute("confirm-button-class") ?? "btn-primary";
        confirmButton.className += " " + confirmButtonExtraClass;

        const showButton = selectOrError("[slot=show-button]", this);
        showButton.addEventListener("click", event => {
            event.stopPropagation();
            this.dialog.showModal();
        });
        const updateDisabledAttribute = () => {
            this.toggleAttribute("disabled", showButton.hasAttribute("disabled"));
        };
        new MutationObserver(updateDisabledAttribute).observe(showButton, {
            attributeFilter: ["disabled"],
        });
        updateDisabledAttribute();

        this.dialogForm = selectOrError("form[method=dialog]", this.dialog);
        this.dialogForm.addEventListener("submit", this.onDialogFormSubmit);

        this.dialog.addEventListener("click", event => event.stopPropagation());
    }

    onDialogFormSubmit = (event: SubmitEvent) => {
        event.preventDefault();

        const isConfirm = event.submitter?.dataset.eventType === "confirm";

        if (isConfirm && this.internals.form && !this.internals.form.reportValidity()) {
            return;
        }

        this.closeDialogSlowly();

        if (isConfirm) {
            if (this.type === "submit") {
                // Unfortunately, `this` cannot act as the submitter of the form. Instead, we make our `value` attribute
                // visible to the form until submission is finished (the `submit` handlers of the form might cancel the
                // submission again, which is why we hide reset the visible value again afterwards).
                this.internals.setFormValue(this.getAttribute("value"));
                this.internals.form?.requestSubmit();
                this.internals.setFormValue(null);
            } else {
                this.dispatchEvent(new CustomEvent("confirmed", { detail: new FormData(this.dialogForm) }));
            }
        }
    };

    closeDialogSlowly = () => {
        this.dialog.addEventListener(
            "animationend",
            () => {
                this.dialog.removeAttribute("closing");
                this.dialog.close();
            },
            { once: true },
        );
        this.dialog.setAttribute("closing", "");
    };
}
