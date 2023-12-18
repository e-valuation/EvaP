import "./translation.js";
import { unwrap, assert, selectOrError } from "./utils.js";

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

class NotebookLogic {
    private readonly notebookCard: HTMLElement;
    private readonly evapContent: HTMLElement;
    private readonly formLogic: NotebookFormLogic;
    private readonly localStorageKey: string;
    private readonly collapseNotebookButtonSelector: string;

    constructor(notebookSelector: string, noteBookFormSelector: string, evapContentSelector: string, localStorageKey: string, collapseNotebookButtonSelector: string) {
        this.notebookCard = selectOrError(notebookSelector);
        this.formLogic = new NotebookFormLogic(noteBookFormSelector);
        this.evapContent = selectOrError(evapContentSelector);
        this.localStorageKey = localStorageKey + "_" + notebookSelector;
        this.collapseNotebookButtonSelector = collapseNotebookButtonSelector;
    }

    private onShowNotebook = (): void => {
        this.notebookCard.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.evapContent.classList.add("notebook-margin");
        selectOrError(this.collapseNotebookButtonSelector).classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebookCard.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.evapContent.classList.remove("notebook-margin");
        selectOrError(this.collapseNotebookButtonSelector).classList.replace("hide", "show");
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


export function initNotebook(notebookSelector: string, noteBookFormSelector: string, evapContentSelector: string, localStorageKey: string, collapseNotebookButtonSelector: string): void {
    if (document.querySelector(notebookSelector) && document.querySelector(noteBookFormSelector) && document.querySelector(evapContentSelector) && localStorageKey && collapseNotebookButtonSelector) {

    new NotebookLogic(notebookSelector, noteBookFormSelector, evapContentSelector, localStorageKey, collapseNotebookButtonSelector).attach();}
}