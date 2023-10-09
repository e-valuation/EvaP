import { unwrap, assert, selectOrError } from "./utils.js";

const NOTEBOOK_LOCALSTORAGE_KEY = "evap_notebook_open";
const COLLAPSE_TOGGLE_BUTTON_ID = "notebookButton";
const WEBSITE_CONTENT_ID = "evapContent";
const NOTEBOOK_FORM_ID = "notebook-form";

class NotebookFormLogic {
    private readonly notebook: HTMLFormElement;
    private readonly updateCooldown = 2000;

    constructor(notebookFormId: string) {
        this.notebook = selectOrError(notebookFormId);
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
                this.notebook.setAttribute("data-state", "ready");
                submitter.disabled = false;
                alert(submitter.dataset.errormessage);
            });
    };

    public attach = (): void => {
        this.notebook.addEventListener("submit", this.onSubmit);
    };
}

export class NotebookLogic {
    private readonly notebookCard: HTMLElement;
    private readonly evapContent: HTMLElement;
    private formLogic: NotebookFormLogic;
    private readonly localStorageKey: string;

    constructor(notebookId: string) {
        this.notebookCard = unwrap(document.getElementById(notebookId));
        this.formLogic = new NotebookFormLogic(NOTEBOOK_FORM_ID);
        this.evapContent = unwrap(document.getElementById(WEBSITE_CONTENT_ID));
        this.localStorageKey = NOTEBOOK_LOCALSTORAGE_KEY + "_" + this.notebookCard.dataset.notebookId;
    }

    private onShowNotebook = (): void => {
        this.notebookCard.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.evapContent.classList.add("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebookCard.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.evapContent.classList.remove("notebook-margin");
        unwrap(document.getElementById(COLLAPSE_TOGGLE_BUTTON_ID)).classList.replace("hide", "show");
    };

    public attach = (): void => {
        if (localStorage.getItem(this.localStorageKey) == "true") {
            this.notebookCard.classList.add("show");
            this.onShowNotebook();
        }

        this.notebookCard.addEventListener("show.bs.collapse", this.onShowNotebook);
        this.notebookCard.addEventListener("hidden.bs.collapse", this.onHideNotebook);

        this.formLogic.attach();
    };
}
