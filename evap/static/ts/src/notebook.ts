import "./translation.js";
import { unwrap, assert } from "./utils.js";

class NotebookFormLogic {
    private readonly notebook: HTMLFormElement;
    private readonly updateCooldown = 2000;

    constructor(notebook: HTMLFormElement) {
        this.notebook = notebook;
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
    private readonly collapseNotebookButton: HTMLElement;

    constructor(
        notebook: HTMLElement,
        notebookForm: HTMLFormElement,
        evapContent: HTMLElement,
        collapseNotebookButton: HTMLElement,
        localStorageKey: string,
    ) {
        this.notebookCard = notebook;
        this.formLogic = new NotebookFormLogic(notebookForm);
        this.evapContent = evapContent;
        this.localStorageKey = localStorageKey;
        this.collapseNotebookButton = collapseNotebookButton;
    }

    private onShowNotebook = (): void => {
        this.notebookCard.classList.add("notebook-container");

        localStorage.setItem(this.localStorageKey, "true");
        this.evapContent.classList.add("notebook-margin");
        this.collapseNotebookButton.classList.replace("show", "hide");
    };

    private onHideNotebook = (): void => {
        this.notebookCard.classList.remove("notebook-container");

        localStorage.setItem(this.localStorageKey, "false");
        this.evapContent.classList.remove("notebook-margin");
        this.collapseNotebookButton.classList.replace("hide", "show");
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
