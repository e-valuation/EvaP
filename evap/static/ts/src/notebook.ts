declare const bootstrap: typeof import("bootstrap");
import { unwrap, assert } from "./utils.js";

const NOTEBOOK_LOCALSTORAGE_KEY = "evap_notebook_open";
const COLLAPSE_TOGGLE_BUTTON_ID = "notebookButton";
const WEBSITE_CONTENT_ID = "evapContent";
const NOTEBOOK_FORM_ID = "notebook-form";

class NotebookFormLogic {
    private readonly notebook: HTMLFormElement;
    private readonly updateCooldown = 2000;

    constructor(notebookFormId: string) {
        this.notebook = unwrap(document.getElementById(notebookFormId)) as HTMLFormElement;
    }

    private onSubmit = (event: SubmitEvent): void => {
        event.preventDefault();

        const submitter = unwrap(event.submitter) as HTMLButtonElement;
        submitter.disabled = true;
        this.notebook.setAttribute("data-state", "sending");

        fetch(this.notebook.action, {
            body: new FormData(this.notebook),
            method: "POST",
        })
            .then(response => {
                assert(response.ok);
                this.notebook.setAttribute("data-state", "successful");
                setTimeout(() => {
                    this.notebook.setAttribute("data-state", "ready");
                    submitter.disabled = false;
                }, this.updateCooldown);
            })
            .catch(() => {
                this.notebook.setAttribute("data-state", "error");
                submitter.disabled = false;
                alert(submitter.dataset.errormessage);
            });
    };

    public attach = (): void => {
        this.notebook.addEventListener("submit", this.onSubmit);
    };
}

export class NotebookLogic {
    private readonly notebook_card: HTMLElement;
    private readonly evapContent: HTMLElement;
    private formLogic: NotebookFormLogic;
    private readonly localStorageKey: string;

    constructor(notebookId: string) {
        this.notebook_card = unwrap(document.getElementById(notebookId));
        this.formLogic = new NotebookFormLogic(NOTEBOOK_FORM_ID);
        this.evapContent = unwrap(document.getElementById(WEBSITE_CONTENT_ID));
        this.localStorageKey = NOTEBOOK_LOCALSTORAGE_KEY + "_" + this.notebook_card.dataset.notebookId;
    }

    private onShowNotebook = (): void => {
        this.notebook_card.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.evapContent.classList.add("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebook_card.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.evapContent.classList.remove("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("hide", "show");
    };

    public attach = (): void => {
        if (localStorage.getItem(this.localStorageKey) == "true") {
            this.notebook_card.classList.add("show");
            this.onShowNotebook();
        }

        this.notebook_card.addEventListener("show.bs.collapse", this.onShowNotebook);
        this.notebook_card.addEventListener("hidden.bs.collapse", this.onHideNotebook);

        this.formLogic.attach();
    };
}
