import "./translation.js";
import { unwrap, assert, selectOrError } from "./utils.js";

const NOTEBOOK_LOCALSTORAGE_KEY = "evap_notebook_open";
const COLLAPSE_TOGGLE_BUTTON_SELECTOR = "#notebookButton";
const WEBSITE_CONTENT_SELECTOR = "#evapContent";
const NOTEBOOK_FORM_SELECTOR = "#notebook-form";

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
                alert(window.gettext("The server is not responding."));
            });
    };

    public attach = (): void => {
        this.notebook.addEventListener("submit", this.onSubmit);
    };
}

export class NotebookLogic {
    private readonly notebookCard: HTMLElement;
    private readonly evapContent: HTMLElement;
    private readonly formLogic: NotebookFormLogic;
    private readonly localStorageKey: string;

    constructor(notebookSelector: string) {
        this.notebookCard = selectOrError(notebookSelector);
        this.formLogic = new NotebookFormLogic(NOTEBOOK_FORM_SELECTOR);
        this.evapContent = selectOrError(WEBSITE_CONTENT_SELECTOR);
        this.localStorageKey = NOTEBOOK_LOCALSTORAGE_KEY + "_" + notebookSelector;
    }

    private onShowNotebook = (): void => {
        this.notebookCard.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.evapContent.classList.add("notebook-margin");
        selectOrError(COLLAPSE_TOGGLE_BUTTON_SELECTOR).classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebookCard.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.evapContent.classList.remove("notebook-margin");
        selectOrError(COLLAPSE_TOGGLE_BUTTON_SELECTOR).classList.replace("hide", "show");
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
