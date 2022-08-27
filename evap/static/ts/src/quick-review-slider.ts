declare const bootstrap: typeof import("bootstrap");

import { saneParseInt, assertDefined, selectOrError, clamp, assert } from "./utils";
import { CSRF_HEADERS } from "./csrf-utils";

type SubmitterElement = HTMLInputElement | HTMLButtonElement;
type SlideDirection = "left" | "right";
// TODO: narrow
type Action = string;

enum StartOverWhere {
    Undecided,
    All,
}

enum Layer {
    Answer = 0,
    Question = 1,
    Questionnaire = 2,
}

interface NavigationButtonWithCounters {
    button: HTMLElement;
    reviewedCounter: HTMLElement;
    unreviewedCounter: HTMLElement;
}

const submitSelectorForAction = (action: Action) => `[type=submit][name=action][value=${action}]`;

export class QuickReviewSlider {
    slider: HTMLElement;
    sliderItems: Array<HTMLElement>;
    slideTriggers: Array<HTMLElement>;
    skipEvaluationButton: HTMLElement;

    answerSlides: Array<HTMLElement> = [];
    alertSlide: HTMLElement;
    alertContentSpans: { unreviewed: HTMLElement; reviewed: HTMLElement };
    startOverTriggers: { undecided: HTMLElement; all: HTMLElement };

    navigationButtons: { left: NavigationButtonWithCounters; right: NavigationButtonWithCounters };

    updateForm: HTMLFormElement;

    selectedSlideIndex: number = 0;
    nextEvaluationIndex: number = 0;

    evaluationSkipUrl: URL;

    constructor(slider: HTMLElement, updateForm: HTMLFormElement, evaluationSkipUrl: URL) {
        this.slider = slider;
        this.updateForm = updateForm;
        this.evaluationSkipUrl = evaluationSkipUrl;

        this.sliderItems = Array.from(this.slider.querySelectorAll(".slider-item"));
        this.slideTriggers = Array.from(this.slider.querySelectorAll("[data-slide]"));
        // TODO: is there always exactly one?
        this.skipEvaluationButton = selectOrError("[data-skip-evalaution]");
        this.alertSlide = selectOrError(".alert", this.slider);

        this.startOverTriggers = {
            undecided: selectOrError("[data-startover=undecided]", this.slider),
            all: selectOrError("[data-startover=all]", this.slider),
        };
        this.alertContentSpans = {
            unreviewed: selectOrError("[data-content=unreviewed]", this.alertSlide),
            reviewed: selectOrError("[data-content=reviewed]", this.alertSlide),
        };
        this.navigationButtons = {
            left: {
                button: selectOrError(".slider-side-left", this.slider),
                reviewedCounter: selectOrError("[data-counter=reviewed-left]", this.slider),
                unreviewedCounter: selectOrError("[data-counter=unreviewed-left]", this.slider),
            },
            right: {
                button: selectOrError(".slider-side-left", this.slider),
                reviewedCounter: selectOrError("[data-counter=reviewed-left]", this.slider),
                unreviewedCounter: selectOrError("[data-counter=unreviewed-left]", this.slider),
            },
        };
    }

    //
    // State
    //
    isShowingEndslide() {
        return this.selectedSlideIndex === this.answerSlides.length;
    }
    get selectedSlide() {
        return this.answerSlides[this.selectedSlideIndex];
    }

    //
    // DOM
    //
    attach() {
        this.updateForm.addEventListener("submit", this.formSubmitHandler);
        document.addEventListener("keydown", this.keydownHandler);
        this.skipEvaluationButton.addEventListener("click", this.skipEvaluationHandler);
        this.sliderItems.forEach(item =>
            item.addEventListener("transitionend", () => {
                this.updateButtons();
                item.classList.remove("to-left", "to-right");
                item.style.top = "";
                item.style.height = "";
            }),
        );
        this.slideTriggers.forEach(trigger =>
            trigger.addEventListener("click", () => {
                const offset = trigger.dataset.slide === "left" ? -1 : 1;
                this.slideTo(this.selectedSlideIndex + offset);
                this.updateButtons();
            }),
        );

        this.startOver(StartOverWhere.Undecided);
        this.updateNextEvaluation();
    }

    formSubmitHandler(event: SubmitEvent) {
        const actionButton = event.submitter as SubmitterElement | null;
        assertDefined(actionButton);
        assert(actionButton.name === "action");
        if (this.isShowingEndslide() || this.isWrongSubmit(actionButton)) {
            event.preventDefault();
            return;
        }

        // Update UI after submit is done (https://stackoverflow.com/q/71473512/13679671)
        setTimeout(() => this.reviewAction(actionButton.value));
    }
    keydownHandler(event: KeyboardEvent) {
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            return;
        }

        const clickTargetSelectors = new Map([
            ["arrowleft", "[data-slide=left]"],
            ["arrowright", "[data-slide=right]"],
            ["j", submitSelectorForAction("publish")],
            ["k", submitSelectorForAction("make_private")],
            ["l", submitSelectorForAction("delete")],
            ["backspace", submitSelectorForAction("unreview")],
            ["e", submitSelectorForAction("textanswer_edit")],
            ["enter", `[data-url=next-evaluation][data-next-evaluation-index="${this.nextEvaluationIndex}"]`],
            ["m", "[data-startover=undecided]"],
            ["n", "[data-startover=all]"],
            ["s", "[data-skip-evaluation]"],
        ]);
        const selector = clickTargetSelectors.get(event.key.toLowerCase());

        if (selector && !event.repeat) {
            this.slider.querySelector<HTMLElement>(selector)?.click();
            event.preventDefault();
        }
    }
    async skipEvaluationHandler(_event: Event) {
        const idElement = document.querySelector<HTMLElement>("[data-evaluation]:not(:hidden)");
        if (!idElement) {
            return;
        }

        this.nextEvaluationIndex++;
        this.updateNextEvaluation();

        const skippedEvaluationId = idElement.dataset.evaluation;
        assertDefined(skippedEvaluationId);

        try {
            const response = await fetch(this.evaluationSkipUrl, {
                method: "POST",
                body: new URLSearchParams({ evaluation_id: skippedEvaluationId }),
                headers: CSRF_HEADERS,
            });
            assert(response.ok);
        } catch (err) {
            // TODO: translation?
            window.alert("The server is not responding.");
            console.error(err);
        }
    }
    reviewAction(action: Action) {
        if (action === "unreview") {
            delete this.selectedSlide.dataset.review;
            this.updateButtons();
        } else {
            this.selectedSlide.dataset.review = action;
            this.updateButtonsActive();
        }

        if (["unreview", "textanswer_edit"].includes(action)) {
            return;
        }

        this.slideTo(this.selectedSlideIndex + 1);
        const correspondingButtonRight = selectOrError<HTMLElement>(submitSelectorForAction(action), this.slider);
        // TODO: should this trigger an event instead?
        correspondingButtonRight.focus();
    }

    isWrongSubmit(submitter: SubmitterElement) {
        return submitter.value === "make_private" && !("contribution" in this.selectedSlide.dataset);
    }

    //
    // UI Updates
    //
    updateButtons() {
        this.slider
            .querySelectorAll("[data-action-set=reviewing]")
            .forEach(el => el.classList.toggle("d-none", this.isShowingEndslide()));
        this.slider
            .querySelectorAll("[data-action-set=summary]")
            .forEach(el => el.classList.toggle("d-none", !this.isShowingEndslide()));

        if (this.isShowingEndslide()) {
            return;
        }

        this.updateButtonsActive();

        // Update "private" button
        const isContributor = "contribution" in this.selectedSlide.dataset;
        const privateButton = selectOrError<HTMLInputElement>(submitSelectorForAction("make_private"));
        privateButton.disabled = !isContributor;
        const tooltip = bootstrap.Tooltip.getInstance(privateButton);
        assertDefined(tooltip);
        if (isContributor) {
            tooltip.disable();
        } else {
            tooltip.enable();
        }

        // Update "unreview" button
        const isDecided = "review" in this.selectedSlide.dataset;
        const unreviewButton = selectOrError<HTMLInputElement>(submitSelectorForAction("unreview"), this.slider);
        unreviewButton.disabled = !isDecided;
    }
    updateButtonsActive() {
        this.selectedSlide.focus();
        selectOrError<HTMLElement>(".btn:focus", this.slider).blur();

        const activeHighlights = {
            publish: "btn-success",
            make_private: "btn-dark",
            delete: "btn-danger",
        };

        const decision = this.selectedSlide.dataset.review;
        for (const [action, activeHighlight] of Object.entries(activeHighlights)) {
            const btn = selectOrError(submitSelectorForAction(action), this.slider);
            btn.classList.toggle(activeHighlight, decision === action);
            btn.classList.toggle("btn-outline-secondary", decision !== action);
        }
    }
    updateNextEvaluation() {
        let foundNext = false;
        document.querySelectorAll<HTMLElement>("[data-next-evaluation-index]").forEach(element => {
            const isNext = saneParseInt(element.dataset.nextEvaluationIndex!) === this.nextEvaluationIndex;
            element.classList.toggle("d-none", !isNext);
            foundNext ||= isNext;
        });
        if (!foundNext) {
            this.skipEvaluationButton.classList.add("d-none");
        }
    }

    updateAnswerIdInputs() {
        assertDefined(this.selectedSlide.dataset.id);
        const newAnswerId = saneParseInt(this.selectedSlide.dataset.id);
        assertDefined(newAnswerId);
        for (const input of this.slider.querySelectorAll<HTMLInputElement>("input[name=answer_id]")) {
            input.disabled = saneParseInt(input.value) !== newAnswerId;
        }
    }
    updateNavigationButtons() {
        const leftSlides = this.answerSlides.slice(0, this.selectedSlideIndex);
        const rightSlides = this.answerSlides.slice(this.selectedSlideIndex + 1);
        const leftReviewed = leftSlides.filter(slide => slide.matches("[data-review]")).length;
        const rightReviewed = rightSlides.filter(slide => slide.matches("[data-review]")).length;

        this.navigationButtons.left.button.classList.toggle("visible", this.selectedSlideIndex > 0);
        this.navigationButtons.right.button.classList.toggle("visible", !this.isShowingEndslide);
        this.navigationButtons.left.reviewedCounter.innerText = leftReviewed.toString();
        this.navigationButtons.left.unreviewedCounter.innerText = (leftSlides.length - leftReviewed).toString();
        this.navigationButtons.right.reviewedCounter.innerText = rightReviewed.toString();
        this.navigationButtons.right.unreviewedCounter.innerText = Math.max(
            rightSlides.length - rightReviewed,
            0,
        ).toString();
    }

    //
    // Sliding
    //
    startOver(where: StartOverWhere) {
        const decided = this.slider.querySelectorAll<HTMLElement>(`[data-layer=${Layer.Questionnaire}][data-review]`);
        const undecided = this.slider.querySelectorAll<HTMLElement>(
            `[data-layer=${Layer.Questionnaire}]:not([data-review])`,
        );
        this.answerSlides = Array.from(decided).concat(Array.from(undecided));

        const startIndex = where === StartOverWhere.Undecided && undecided.length > 0 ? decided.length : 0;
        this.slideTo(startIndex);
        this.updateButtons();
    }
    slideTo(requestedIndex: number) {
        requestedIndex = clamp(requestedIndex, 0, this.answerSlides.length);
        const direction = requestedIndex >= this.selectedSlideIndex ? "right" : "left";
        this.selectedSlideIndex = requestedIndex;

        if (this.isShowingEndslide()) {
            const slidesExist = this.answerSlides.length > 0;
            const allAreReviewed = this.answerSlides.every(slide => slide.matches("[data-review]"));

            this.alertSlide.classList.toggle("alert-secondary", !slidesExist);
            this.alertSlide.classList.toggle("alert-warning", !allAreReviewed);
            this.alertSlide.classList.toggle("alert-success", slidesExist && allAreReviewed);
            this.alertContentSpans.unreviewed.classList.toggle("d-none", allAreReviewed);
            this.alertContentSpans.reviewed.classList.toggle("d-none", !allAreReviewed);
            this.startOverTriggers.undecided.classList.toggle("d-none", allAreReviewed);
            this.startOverTriggers.all.classList.toggle("d-none", !slidesExist);
            this.slideLayer(Layer.Questionnaire, direction, this.alertSlide);
        } else {
            this.slideLayer(Layer.Questionnaire, direction, this.selectedSlide);
            this.updateAnswerIdInputs();
        }

        this.updateNavigationButtons();
    }
    slideLayer(layer: Layer, direction: SlideDirection, element?: HTMLElement) {
        if (element?.classList.contains("active")) {
            return;
        }
        const last = this.slider.querySelector<HTMLElement>(`[data-layer=${layer}].active, .alert.active`);
        if (last) {
            const reversed: SlideDirection = direction === "left" ? "right" : "left";
            last.style.top = `${last.offsetTop}px`;
            last.style.height = `${last.getBoundingClientRect().height}px`;
            last.classList.remove("active", "to-left", "to-right");
            last.classList.add(`to-${reversed}`);
        }

        if (layer > 0) {
            const reference = (element?.previousElementSibling || undefined) as HTMLElement | undefined;
            this.slideLayer(layer - 1, direction, reference);
        }

        if (element) {
            // TODO: Why the calls to .position() (jQuery) inbetween?
            element.classList.remove("to-left", "to-right");
            element.classList.add(`to-${direction}`, "active");
        }
    }
}
