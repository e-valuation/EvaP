import { selectOrError, assert } from "./utils.js";
import { AutoFormSaver } from "./auto-form-saver.js";
import { CSRF_HEADERS } from "./csrf-utils.js";
import { initTextAnswerWarnings } from "./text-answer-warnings.js";
import { Collapse } from "bootstrap";

function isInvisible(el: Element): boolean {
    if (getComputedStyle(el).display === "none") {
        return true;
    }
    return el.parentElement !== null && isInvisible(el.parentElement);
}

function hasTabbingTarget(element: HTMLElement): boolean {
    return element.querySelector(".tab-selectable") !== null;
}
console.log("here");

function selectByNumberKey(row: HTMLElement, num: number) {
    let index = 2 * num - 1;
    if (num === 0) {
        // Select "No answer"
        index = row.children.length - 1;
    }

    if (!(0 <= index && index < row.children.length)) {
        return;
    }

    const nextElement = row.children[index] as HTMLElement;
    nextElement.click();
}

const studentForm = selectOrError<HTMLFormElement>("#student-vote-form");
const selectables: NodeListOf<HTMLElement> = studentForm.querySelectorAll(".tab-selectable");
const rows = Array.from(studentForm.getElementsByClassName("tab-row")) as HTMLElement[];
const letterRegex = new RegExp("^[A-Za-zÄÖÜäöü.*+-]$");

// Sometimes we just want the browser to do its thing.
let disableFocusHandler = false;

selectables[0].addEventListener("focus", () => {
    if (disableFocusHandler) {
        disableFocusHandler = false;
        return;
    }

    requestAnimationFrame(() => {
        // When first entering the form area with the altered tabbing rules, we
        // need to make sure that we start on the correct input.
        const correctInput = findCorrectInputInRow(rows[0]);
        if (selectables[0] !== correctInput) {
            fancyFocus(correctInput);
        }
    });
});

studentForm.addEventListener("keydown", (e: KeyboardEvent) => {
    if (e.ctrlKey || e.altKey) {
        return;
    }

    const current = document.activeElement as HTMLElement;
    if (!current.matches("input, label, span, textarea, button")) {
        return;
    }

    if (current.tagName !== "TEXTAREA") {
        // We want to disable backspace, because users may think that
        // they can undo their selection, but they would be sent to the
        // student index (or where they came from otherwise).
        // Additionally, pressing Enter shouldn't submit the form.
        switch (e.key) {
            case "Enter":
                current.click(); // fallthrough
            case "Backspace":
                e.preventDefault();
                return;
        }
    }

    // Since the event could be caught on either the outer label or
    // the nested text / input, the full row could be two steps up
    const currentRow: HTMLElement | null = current.closest(".tab-row");
    if (currentRow === null) {
        return;
    }

    const insideSubmitRow = currentRow.closest(".card-submit-area") !== null;
    if (!insideSubmitRow && current.tagName !== "TEXTAREA") {
        const num = parseInt(e.key);
        if (!isNaN(num)) {
            // Even if the number does not trigger a selection (for example pressing "9"),
            // nothing else should happen, because it would be very frustrating if only some numbers
            // would work as expected.
            e.preventDefault();
            selectByNumberKey(currentRow, num);
            return;
        }
    }

    if (e.key !== "Tab") {
        if (current.tagName !== "TEXTAREA" && letterRegex.test(e.key)) {
            const wholeRow = currentRow.closest("div.row");
            if (wholeRow === null) {
                return;
            }

            e.preventDefault();
            const textAnswerButton: HTMLElement | null = wholeRow.querySelector('[data-bs-toggle="collapse"]');
            const textField: HTMLTextAreaElement | null = wholeRow.querySelector("textarea.tab-selectable");
            if (textAnswerButton !== null && textField !== null) {
                if (isInvisible(textField)) {
                    textAnswerButton.click();
                }
                fancyFocus(textField);
                textField.value += e.key;
                textField.dispatchEvent(new Event("input"));
            }
        }
        return;
    }

    const curRowIndex = rows.indexOf(currentRow);
    const direction = e.shiftKey ? -1 : 1;
    let nextRowIndex = curRowIndex;
    do {
        nextRowIndex += direction;

        if (nextRowIndex === -1) {
            // User wants to tab out in front of the form area
            // To correctly select the first element in front of the form,
            // select the first element tracked by this.
            // Just giving back control to the browser here doesn't work, because
            // it would navigate backwards through the controls of the current row.
            disableFocusHandler = true;
            selectables[0].focus({ preventScroll: true });
            return;
        } else if (nextRowIndex === rows.length) {
            // User wants to tab out behind the form area
            selectables[selectables.length - 1].focus({ preventScroll: true });
            return;
        }
    } while (isInvisible(rows[nextRowIndex]) || !hasTabbingTarget(rows[nextRowIndex]));

    e.preventDefault();
    fancyFocus(findCorrectInputInRow(rows[nextRowIndex]));
});

function findCorrectInputInRow(row: HTMLElement) {
    const alreadySelectedElement = row.querySelector<HTMLElement>(".tab-selectable:checked");

    if (alreadySelectedElement) {
        return alreadySelectedElement;
    }
    const possibleTargets: NodeListOf<HTMLElement> = row.querySelectorAll(".tab-selectable");
    if (possibleTargets.length === 3) {
        // Yes-No / No-Yes question, should focus first element
        return possibleTargets[0];
    }
    // Everything else: The middle of all the answers excluding "no answer"
    // This also handles all the single possibility cases
    const index = Math.floor((possibleTargets.length - 1) / 2);
    return possibleTargets[index];
}

function fancyFocus(element: HTMLElement) {
    element.focus({ preventScroll: true });
    element.scrollIntoView({
        behavior: "smooth",
        block: "center",
    });
}

document.querySelector("#btn-jump-unanswered-question")?.addEventListener("click", scrollToFirstChoiceError);

function scrollToFirstChoiceError() {
    const firstErrorRow = document.querySelector(".row .choice-error");
    const tabRow = firstErrorRow?.closest(".row")?.querySelector<HTMLElement>(".tab-row");
    if (tabRow) {
        fancyFocus(findCorrectInputInRow(tabRow));
    }
}

const dataElement = document.querySelector<HTMLElement>(".dataElement")!;
const evaluationId = dataElement.dataset.evaluation_id!;
const requestUserId = dataElement.dataset.request_user_id;
const languageStorageKey = `student-vote-last-saved-at-${evaluationId}-${requestUserId}`;
const textResultsPublishConfirmation = {
    top: document.querySelector<HTMLInputElement>("#text_results_publish_confirmation_top")!,
    bottom: document.querySelector<HTMLInputElement>("#text_results_publish_confirmation_bottom")!,
    bottomCard: document.querySelector("#bottom_text_results_publish_confirmation_card"),
};

// Ensure that selected questionnaire language is saved and loaded
const params = new URLSearchParams(document.location.search);
const currentlySelectedLanguage = dataElement.dataset.evaluation_language!;
const savedLanguage = localStorage.getItem(languageStorageKey);

if (params.get("language")) {
    localStorage.setItem(languageStorageKey, currentlySelectedLanguage);
} else if (savedLanguage && savedLanguage !== currentlySelectedLanguage) {
    params.set("language", savedLanguage);
    document.location.search = params.toString();
}

const formSaver = new AutoFormSaver(document.getElementById("student-vote-form") as HTMLFormElement, {
    customKeySuffix: `[user=${requestUserId}]`, // don't load data for other users
    onRestore: function () {
        // restore publish confirmation state
        if (textResultsPublishConfirmation.bottomCard) {
            updateTextResultsPublishConfirmation();
        }

        // show all non-empty additional text answer fields
        document.querySelectorAll<HTMLTextAreaElement>(".row-question .collapse textarea").forEach(el => {
            if (el.value.length !== 0) {
                const button = el.closest(".row")!.getElementsByClassName("btn-textanswer")[0] as HTMLButtonElement;
                button.click();
            }
        });
    },
    onSave: function () {
        const timeNow = new Date();
        localStorage.setItem(languageStorageKey, timeNow.toString());
    },
});

const languageCode = dataElement.dataset.language_code!;
function updateLastSavedLabel() {
    const timeNow = new Date();
    const lastSavedLabel = document.getElementById("last-saved")!;
    const lastSavedStorageValue = localStorage.getItem(languageStorageKey);
    if (lastSavedStorageValue !== null) {
        const lastSavedDate = new Date(lastSavedStorageValue);
        const delta = Math.round((timeNow.getTime() - lastSavedDate.getTime()) / 1000);
        const relativeTimeFormat = new Intl.RelativeTimeFormat(languageCode);
        let timeStamp;
        if (delta < 3) {
            timeStamp = "{% translate 'just now' %}";
        } else if (delta < 10) {
            timeStamp = "{% translate 'less than 10 seconds ago' %}";
        } else if (delta < 30) {
            timeStamp = "{% translate 'less than 30 seconds ago' %}";
        } else if (delta < 60) {
            timeStamp = "{% translate 'less than 1 minute ago' %}";
        } else if (delta < 60 * 30) {
            timeStamp = relativeTimeFormat.format(-Math.round(delta / 60), "minutes");
        } else if (delta < 60 * 60 * 12) {
            timeStamp =
                padWithLeadingZeros(lastSavedDate.getHours()) + ":" + padWithLeadingZeros(lastSavedDate.getMinutes());
        } else {
            timeStamp =
                lastSavedDate.getFullYear().toString() +
                "-" +
                padWithLeadingZeros(lastSavedDate.getMonth() + 1) +
                "-" +
                padWithLeadingZeros(lastSavedDate.getDate()) +
                " " +
                padWithLeadingZeros(lastSavedDate.getHours()) +
                ":" +
                padWithLeadingZeros(lastSavedDate.getMinutes());
        }
        lastSavedLabel.innerText = "{% translate 'Last saved locally' %}: " + timeStamp;
    } else {
        lastSavedLabel.innerText = "{% translate 'Could not save your information locally' %}";
    }
}

function padWithLeadingZeros(number: number) {
    return number.toString().padStart(2, "0");
}

// save all data after loading the page
// (the data gets deleted every time the form is submitted, i.e. also when the form had errors and is displayed again)
formSaver.saveAllData();

// Initialize lastSavedLabel and update it every second
updateLastSavedLabel();
setInterval(updateLastSavedLabel, 1000);

const textAnswerWarnings = document.getElementById("text-answer-warnings") as HTMLTextAreaElement;
initTextAnswerWarnings(
    document.querySelectorAll("#student-vote-form textarea"),
    JSON.parse(textAnswerWarnings.textContent) as string[][],
);

const form = document.getElementById("student-vote-form") as HTMLFormElement;
const successMagicString = dataElement.dataset.success_magic_string!;
const successRedirectUrl = dataElement.dataset.success_redirect_url!;
const submitListener = (event: Event) => {
    event.preventDefault(); // don't use the default submission
    const submitButton = document.getElementById("vote-submit-btn") as HTMLButtonElement;
    const originalText = submitButton.innerText;

    submitButton.innerText = "{% translate 'Submitting...' %}";
    submitButton.disabled = true;

    fetch(form.action, {
        body: new FormData(form),
        headers: CSRF_HEADERS,
        method: form.method,
    })
        .then(response => {
            assert(response.ok);
            return response.text();
        })
        .then(response_text => {
            if (response_text === successMagicString) {
                formSaver.releaseData();
                window.location.replace(successRedirectUrl);
            } else {
                // resubmit without this handler to show the site with the form errors
                form.removeEventListener("submit", submitListener);
                form.requestSubmit();
            }
        })
        .catch((_: unknown) => {
            // show a warning if the post isn't successful
            document.getElementById("submit-error-warning")!.classList.remove("d-none");
            submitButton.innerText = originalText;
            submitButton.disabled = false;
        });
};
form.addEventListener("submit", submitListener);

function clearChoiceError(voteButton: HTMLElement) {
    voteButton
        .closest(".row")!
        .querySelectorAll(".choice-error")
        .forEach(highlightedElement => {
            highlightedElement.classList.remove("choice-error");
        });
}

console.log("here");
document.querySelectorAll<HTMLButtonElement>("[data-mark-no-answers-for]").forEach(button => {
    console.log("here");
    const contributorId = button.dataset.markNoAnswersFor!;
    const voteArea = document.getElementById(`vote-area-${contributorId}`)!;
    const collapseToggle = voteArea.closest(".collapsible")!.querySelector(".collapse-toggle")!;

    button.addEventListener("click", () => {
        voteArea.querySelectorAll<HTMLInputElement>(".vote-inputs [type=radio][value='6']").forEach(radioInput => {
            radioInput.checked = true;
            clearChoiceError(radioInput);
        });

        formSaver.saveAllData();

        // hide questionnaire for contributor
        const voteAreaCollapse = Collapse.getOrCreateInstance(voteArea);
        voteAreaCollapse.hide();
        collapseToggle.classList.add("tab-selectable");

        // Disable this button, until user changes a value
        button.classList.remove("tab-selectable");
        button.disabled = true;
    });

    voteArea.querySelectorAll(".vote-inputs [type=radio]:not([value='6'])").forEach(radioInput => {
        radioInput.addEventListener("click", () => {
            collapseToggle.classList.remove("tab-selectable");
            button.classList.add("tab-selectable");
            button.disabled = false;
        });
    });

    collapseToggle.addEventListener("click", () => {
        if (button.classList.contains("tab-selectable")) {
            collapseToggle.classList.remove("tab-selectable");
        }
    });
});

// remove error highlighting when an answer was selected
document.querySelectorAll<HTMLLabelElement>(".vote-btn.choice-error").forEach(voteButton => {
    voteButton.addEventListener("click", () => clearChoiceError(voteButton));
    console.log(voteButton.attributes);
    const actualInput = document.getElementById(voteButton.htmlFor)!;
    actualInput.addEventListener("click", () => clearChoiceError(voteButton));
});

document.querySelectorAll<HTMLButtonElement>(".btn-textanswer").forEach(textanswerButton => {
    const textfieldClass = textanswerButton.dataset.bsTarget!;
    const textfield = textanswerButton
        .closest(".row")!
        .querySelector<HTMLTextAreaElement>(textfieldClass + " textarea")!;
    textanswerButton.addEventListener("click", () => {
        // focus textarea when opening the collapsed area
        const isOpening = textanswerButton.classList.contains("collapsed");
        if (isOpening) {
            requestAnimationFrame(() => {
                textfield.focus();
            });
        }
    });
    textfield.addEventListener("input", () => {
        if (textfield.value.trim().length !== 0) {
            textanswerButton.classList.add("has-contents");
        } else {
            textanswerButton.classList.remove("has-contents");
        }
    });
    textfield.dispatchEvent(new Event("input"));
});

// handle text_results_publish_confirmation checkbox changes
function updateTextResultsPublishConfirmation() {
    const isChecked = textResultsPublishConfirmation.top.checked;
    textResultsPublishConfirmation.bottom.checked = isChecked;
    textResultsPublishConfirmation.bottomCard?.classList.toggle("d-none", isChecked);
}

if (textResultsPublishConfirmation.bottomCard) {
    textResultsPublishConfirmation.top.addEventListener("change", updateTextResultsPublishConfirmation);
    textResultsPublishConfirmation.bottom.addEventListener("change", () => {
        // The top checkbox should only be visually checked without triggering the change event,
        // which would hide the bottom card.
        // To keep the top checkbox checked (after a reload or submit), save the form manually.
        textResultsPublishConfirmation.top.checked = textResultsPublishConfirmation.bottom.checked;
        formSaver.saveAllData();
    });
}
