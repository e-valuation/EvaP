import "./translation.js";
import { unwrap, assert } from "./utils.js";

class NotebookFormLogic {
    private readonly updateCooldown = 2000;

    constructor(private readonly notebook: HTMLFormElement) {}

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
    private readonly formLogic: NotebookFormLogic;

    constructor(
        private readonly notebookCard: HTMLElement,
        notebookForm: HTMLFormElement,
        private readonly evapContent: HTMLElement,
        private readonly collapseNotebookButton: HTMLElement,
        private readonly localStorageKey: string,
    ) {
        this.formLogic = new NotebookFormLogic(notebookForm);
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
