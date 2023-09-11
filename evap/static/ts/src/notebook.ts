declare const bootstrap: typeof import("bootstrap");
import { unwrap, assert } from "./utils.js";

const NOTEBOOK_LOCALSTORAGE_KEY = "evap_notebook_open";
const COLLAPSE_TOGGLE_BUTTON_ID = "notebookButton";
const WEBSITE_CONTENT_ID = "evapContent";
const NOTEBOOK_FORM_ID = "notebook-form";

class NotebookFormLogic {
    private readonly notebook: HTMLFormElement;

    constructor(notebookFormId: string) {
        this.notebook = unwrap(document.getElementById(notebookFormId)) as HTMLFormElement;
    }

    private onSubmit = (event: SubmitEvent): void => {
        event.preventDefault();
        event.stopPropagation();

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
                }, 2000);
            })
            .catch(() => {
                this.notebook.setAttribute("data-state", "error");
                submitter.disabled = false;
                alert(submitter.dataset.error);
            });
    };

    public attach = (): void => {
        unwrap(this.notebook).addEventListener("submit", this.onSubmit);
    };
}

export class NotebookLogic {
    private readonly notebook: HTMLElement;
    private readonly content: HTMLElement;
    private form: NotebookFormLogic;
    private readonly localStorageKey: string;

    constructor(notebookId: string) {
        this.notebook = unwrap(document.getElementById(notebookId));
        this.form = new NotebookFormLogic(NOTEBOOK_FORM_ID);
        this.content = unwrap(document.getElementById(WEBSITE_CONTENT_ID));
        this.localStorageKey = NOTEBOOK_LOCALSTORAGE_KEY;
    }

    private onShowNotebook = (): void => {
        this.notebook.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.content.classList.add("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebook.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.content.classList.remove("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("hide", "show");
    };

    public attach = (): void => {
        if (localStorage.getItem(this.localStorageKey) == "true") {
            this.notebook.classList.add("show");
            this.onShowNotebook();
        }

        this.notebook.addEventListener("show.bs.collapse", this.onShowNotebook);
        this.notebook.addEventListener("hidden.bs.collapse", this.onHideNotebook);

        this.form.attach();
    };
}
