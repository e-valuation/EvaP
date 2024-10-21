// This file accompanies the "quick" view in the textanswer review site. The quick view presents textanswers in a
// _slider_ that is made up of three layers - answer, question and questionnaire. One answer is shown at a time, it is
// _active_. The slider contains a form that has multiple submit buttons, one for each review decision, one for revoking
// a previous decision and one for editing the answer. If a review decision is made, the next answer slides in from the
// right. At the end, there is one _alert slide_ that summarizes the current state of affairs regarding textanswer
// review. The alert slide may also be the active slide. From there, users can _start over_ and look at _all_ or only
// _undecided_ answers again. The alert slide also shows _next evaluations_ that need textanswer reviewing and an option
// to skip the currently suggested evaluation.

declare const bootstrap: typeof import("bootstrap");

import { CSRF_HEADERS } from "./csrf-utils.js";
import {
    assert,
    assertDefined,
    clamp,
    findPreviousElementSibling,
    isVisible,
    saneParseInt,
    selectOrError,
} from "./utils.js";

type SubmitterElement = HTMLInputElement | HTMLButtonElement;
type SlideDirection = "left" | "right";

enum Action {
    Delete = "delete",
    MakePrivate = "make_private",
    Publish = "publish",
    TextanswerEdit = "textanswer_edit",
    Unreview = "unreview",
}

enum StartOverWhere {
    Undecided,
    All,
}

enum Layer {
    Questionnaire = 0,
    Question = 1,
    Answer = 2,
}

interface NavigationButtonWithCounters {
    button: HTMLElement;
    reviewedCounter: HTMLElement;
    unreviewedCounter: HTMLElement;
}

const submitSelectorForAction = (action: Action) => `[type=submit][name=action][value=${action}]`;
const inputSelectorForFlagState = (isFlagged: boolean) => `input[name="is_flagged"][value=${isFlagged.toString()}]`;

export class QuickReviewSlider {
    private readonly slider: HTMLElement;
    private readonly reviewDecisionForm: HTMLFormElement;
    private readonly flagForm: HTMLFormElement;
    private readonly sliderItems: Array<HTMLElement>;
    private answerSlides: Array<HTMLElement> = [];
    private selectedSlideIndex = 0;

    private readonly alertSlide: HTMLElement;
    private readonly alertContentSpans: { unreviewed: HTMLElement; reviewed: HTMLElement };
    private readonly skipEvaluationButton: HTMLElement | null;
    private readonly evaluationSkipUrl: string;
    private nextEvaluationIndex = 0;

    private readonly startOverTriggers: { undecided: HTMLElement; all: HTMLElement };
    private readonly slideTriggers: Array<HTMLElement>;
    private readonly navigationButtons: { left: NavigationButtonWithCounters; right: NavigationButtonWithCounters };

    constructor(
        slider: HTMLElement,
        reviewDecisionForm: HTMLFormElement,
        flagForm: HTMLFormElement,
        evaluationSkipUrl: string,
    ) {
        this.slider = slider;
        this.reviewDecisionForm = reviewDecisionForm;
        this.flagForm = flagForm;
        this.evaluationSkipUrl = evaluationSkipUrl;

        this.sliderItems = Array.from(this.slider.querySelectorAll(".slider-item"));
        this.slideTriggers = Array.from(this.slider.querySelectorAll("[data-slide]"));
        this.skipEvaluationButton = document.querySelector("[data-skip-evaluation]");
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
                button: selectOrError(".slider-side-right", this.slider),
                reviewedCounter: selectOrError("[data-counter=reviewed-right]", this.slider),
                unreviewedCounter: selectOrError("[data-counter=unreviewed-right]", this.slider),
            },
        };
    }

    //
    // State
    //
    public get selectedSlide(): HTMLElement {
        assert(!this.isShowingEndslide(), "No answer slide is selected!");
        return this.answerSlides[this.selectedSlideIndex];
    }
    public isShowingEndslide = () => this.selectedSlideIndex === this.answerSlides.length;

    //
    // DOM
    //
    public attach = () => {
        this.reviewDecisionForm.addEventListener("submit", this.reviewDecisionFormSubmitHandler);
        this.flagForm.addEventListener("submit", this.flagFormSubmitHandler);
        this.slider.querySelectorAll<HTMLInputElement>("input[name=is_flagged]").forEach(isFlaggedInput => {
            isFlaggedInput.addEventListener("change", () => {
                assertDefined(isFlaggedInput.form);
                isFlaggedInput.form.requestSubmit();
            });
        });
        document.addEventListener("keydown", this.keydownHandler);
        this.skipEvaluationButton?.addEventListener("click", this.skipEvaluationHandler);
        this.sliderItems.forEach(item => item.addEventListener("transitionend", this.transitionHandler(item)));
        this.slideTriggers.forEach(trigger => trigger.addEventListener("click", this.slideHandler(trigger)));
        Object.values(this.startOverTriggers).forEach(trigger =>
            trigger.addEventListener("click", this.startOverHandler(trigger)),
        );

        this.startOver(StartOverWhere.Undecided);
        this.updateNextEvaluation();
    };

    private reviewDecisionFormSubmitHandler = (event: SubmitEvent) => {
        const actionButton = event.submitter as SubmitterElement | null;
        try {
            assertDefined(actionButton);
            assert(actionButton.name === "action");
            assert(Object.values<string>(Action).includes(actionButton.value)); // button value is valid Action
        } catch (err) {
            event.preventDefault();
            throw err;
        }
        const action = actionButton.value as Action;

        if (this.isShowingEndslide() || this.isWrongSubmit(actionButton)) {
            event.preventDefault();
            return;
        }

        // Update UI after submit is done (https://stackoverflow.com/q/71473512/13679671)
        setTimeout(() => {
            assert(action !== Action.TextanswerEdit, "You should have been redirected already.");

            if (action === Action.Unreview) {
                delete this.selectedSlide.dataset.review;
            } else {
                this.selectedSlide.dataset.review = action;
            }
            this.updateButtons();

            const actionsThatSlide = [Action.Delete, Action.MakePrivate, Action.Publish];
            if (!actionsThatSlide.includes(action)) {
                return;
            }

            this.slideTo(this.selectedSlideIndex + 1);
            const correspondingButtonRight = selectOrError<HTMLElement>(submitSelectorForAction(action), this.slider);
            correspondingButtonRight.focus();
        });
    };
    private flagFormSubmitHandler = (_event: SubmitEvent) => {
        const newIsFlagged = new FormData(this.flagForm).get("is_flagged") == "true";
        if (newIsFlagged) {
            this.selectedSlide.dataset.isFlagged = "";
        } else {
            delete this.selectedSlide.dataset.isFlagged;
        }
    };
    private keydownHandler = (event: KeyboardEvent) => {
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            return;
        }

        const clickTargetSelectors = new Map([
            ["arrowleft", "[data-slide=left]"],
            ["arrowright", "[data-slide=right]"],
            ["j", submitSelectorForAction(Action.Publish)],
            ["k", submitSelectorForAction(Action.MakePrivate)],
            ["l", submitSelectorForAction(Action.Delete)],
            ["backspace", submitSelectorForAction(Action.Unreview)],
            ["e", submitSelectorForAction(Action.TextanswerEdit)],
            ["f", inputSelectorForFlagState(true)],
            ["d", inputSelectorForFlagState(false)],
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
    };
    private skipEvaluationHandler = async (_event: Event) => {
        const idElement = Array.from(document.querySelectorAll<HTMLElement>("[data-evaluation]")).find(isVisible);
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
                headers: CSRF_HEADERS,
                body: new URLSearchParams({ evaluation_id: skippedEvaluationId }),
            });
            assert(response.ok);
        } catch (err) {
            window.alert("The server is not responding.");
            console.error(err);
        }
    };

    private isWrongSubmit = (submitter: SubmitterElement) => {
        return (submitter.value as Action) === Action.MakePrivate && !("contribution" in this.selectedSlide.dataset);
    };

    private transitionHandler = (item: HTMLElement) => () => {
        this.updateButtons();
        item.classList.remove("to-left", "to-right");
        item.style.removeProperty("top");
        item.style.removeProperty("height");
    };
    private slideHandler = (trigger: HTMLElement) => () => {
        const offset = trigger.dataset.slide === "left" ? -1 : 1;
        this.slideTo(this.selectedSlideIndex + offset);
        this.updateButtons();
    };
    private startOverHandler = (trigger: HTMLElement) => () => {
        assertDefined(trigger.dataset.startover);
        const mapping = new Map([
            ["undecided", StartOverWhere.Undecided],
            ["all", StartOverWhere.All],
        ]);
        const where = mapping.get(trigger.dataset.startover);
        assertDefined(where);
        this.startOver(where);
    };
    //
    // UI Updates
    //
    private updateButtons = () => {
        this.slider
            .querySelectorAll("[data-action-set=reviewing]")
            .forEach(el => el.classList.toggle("d-none", this.isShowingEndslide()));
        this.slider
            .querySelectorAll("[data-action-set=summary]")
            .forEach(el => el.classList.toggle("d-none", !this.isShowingEndslide()));

        if (this.isShowingEndslide()) {
            return;
        }

        this.updateFocus();
        this.updateDecisionButtonHighlights();
        this.updateFlaggedToggle();

        // Update "private" button
        const isContributor = "contribution" in this.selectedSlide.dataset;
        const privateButton = selectOrError<HTMLInputElement>(submitSelectorForAction(Action.MakePrivate));
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
        const unreviewButton = selectOrError<HTMLInputElement>(submitSelectorForAction(Action.Unreview), this.slider);
        unreviewButton.disabled = !isDecided;
    };
    private updateDecisionButtonHighlights = () => {
        const activeHighlights = new Map([
            [Action.Publish, "btn-success"],
            [Action.MakePrivate, "btn-dark"],
            [Action.Delete, "btn-danger"],
        ]);

        const decision = this.selectedSlide.dataset.review;
        for (const [action, activeHighlight] of activeHighlights.entries()) {
            const btn = selectOrError(submitSelectorForAction(action), this.slider);
            btn.classList.toggle(activeHighlight, decision === action);
            btn.classList.toggle("btn-outline-secondary", decision !== action);
        }
    };
    private updateFlaggedToggle = () => {
        const selector = inputSelectorForFlagState("isFlagged" in this.selectedSlide.dataset);
        const input = selectOrError<HTMLInputElement>(selector, this.slider);
        input.checked = true;
    };
    private updateFocus = () => {
        this.selectedSlide.focus();
        this.slider.querySelector<HTMLElement>(".btn:focus")?.blur();
    };
    private updateNextEvaluation = () => {
        let foundNext = false;
        document.querySelectorAll<HTMLElement>("[data-next-evaluation-index]").forEach(element => {
            const isNext = saneParseInt(element.dataset.nextEvaluationIndex!) === this.nextEvaluationIndex;
            element.classList.toggle("d-none", !isNext);
            foundNext ||= isNext;
        });
        if (!foundNext) {
            this.skipEvaluationButton?.classList.add("d-none");
        }
    };

    private updateAnswerIdInputs = () => {
        let newAnswerId;
        if (!this.isShowingEndslide()) {
            assertDefined(this.selectedSlide.dataset.id);
            newAnswerId = this.selectedSlide.dataset.id;
        }
        for (const input of this.slider.querySelectorAll<HTMLInputElement>("input[name=answer_id]")) {
            input.disabled = input.value !== newAnswerId;
        }
    };
    private updateNavigationButtons = () => {
        const leftSlides = this.answerSlides.slice(0, this.selectedSlideIndex);
        const rightSlides = this.answerSlides.slice(this.selectedSlideIndex + 1);
        const leftReviewed = leftSlides.filter(slide => slide.matches("[data-review]")).length;
        const rightReviewed = rightSlides.filter(slide => slide.matches("[data-review]")).length;

        this.navigationButtons.left.button.classList.toggle("visible", this.selectedSlideIndex > 0);
        this.navigationButtons.right.button.classList.toggle("visible", !this.isShowingEndslide());
        this.navigationButtons.left.reviewedCounter.innerText = leftReviewed.toString();
        this.navigationButtons.left.unreviewedCounter.innerText = (leftSlides.length - leftReviewed).toString();
        this.navigationButtons.right.reviewedCounter.innerText = rightReviewed.toString();
        this.navigationButtons.right.unreviewedCounter.innerText = Math.max(
            rightSlides.length - rightReviewed,
            0,
        ).toString();
    };
    private updateAlertSlide = () => {
        const slidesExist = this.answerSlides.length > 0;
        const allAreReviewed = this.answerSlides.every(slide => "review" in slide.dataset);

        this.alertSlide.classList.toggle("alert-secondary", !slidesExist);
        this.alertSlide.classList.toggle("alert-warning", !allAreReviewed);
        this.alertSlide.classList.toggle("alert-success", slidesExist && allAreReviewed);
        this.alertContentSpans.unreviewed.classList.toggle("d-none", allAreReviewed);
        this.alertContentSpans.reviewed.classList.toggle("d-none", !allAreReviewed);
        this.startOverTriggers.undecided.classList.toggle("d-none", allAreReviewed);
        this.startOverTriggers.all.classList.toggle("d-none", !slidesExist);
    };

    //
    // Sliding
    //
    public startOver = (where: StartOverWhere) => {
        const decided = this.slider.querySelectorAll<HTMLElement>(`[data-layer="${Layer.Answer}"][data-review]`);
        const undecided = this.slider.querySelectorAll<HTMLElement>(
            `[data-layer="${Layer.Answer}"]:not([data-review])`,
        );
        this.answerSlides = Array.from(decided).concat(Array.from(undecided));

        const startOverOnUndecided = where === StartOverWhere.Undecided && undecided.length > 0;
        const startIndex = startOverOnUndecided ? decided.length : 0;
        this.slideTo(startIndex);
        this.updateButtons();
    };
    public slideTo = (requestedIndex: number) => {
        requestedIndex = clamp(requestedIndex, 0, this.answerSlides.length);
        const direction = requestedIndex >= this.selectedSlideIndex ? "right" : "left";
        this.selectedSlideIndex = requestedIndex;

        let nextActiveElement;
        if (this.isShowingEndslide()) {
            nextActiveElement = this.alertSlide;
            this.updateAlertSlide();
        } else {
            nextActiveElement = this.selectedSlide;
        }
        this.slideLayer(Layer.Answer, direction, nextActiveElement);
        this.updateAnswerIdInputs();

        this.updateNavigationButtons();
    };
    private slideLayer = (layer: Layer, direction: SlideDirection, nextActiveElement?: HTMLElement) => {
        // to preserve the vertical positions and heights during transition,
        // the elements will be deactivated from bottom to top and activated from top to bottom

        if (nextActiveElement?.classList.contains("active")) {
            return;
        }
        const last = this.slider.querySelector<HTMLElement>(`[data-layer="${layer}"].active, .alert.active`);
        if (last) {
            const reversed: SlideDirection = direction === "left" ? "right" : "left";
            last.style.top = `${last.offsetTop}px`;
            last.style.height = `${last.getBoundingClientRect().height}px`;
            last.classList.remove("active", "to-left", "to-right");
            last.classList.add(`to-${reversed}`);
        }

        if (layer > Layer.Questionnaire) {
            let activeInParentLayer;
            if (nextActiveElement && !this.isShowingEndslide()) {
                activeInParentLayer =
                    findPreviousElementSibling(nextActiveElement, `[data-layer="${layer - 1}"]`) ?? undefined;
                activeInParentLayer = activeInParentLayer as HTMLElement | undefined;
            }
            this.slideLayer(layer - 1, direction, activeInParentLayer);
        }

        if (nextActiveElement) {
            // We want to slide `nextActiveElement` into the middle from
            // `direction`. To do so, we use a transition on the `transform`
            // and `opacity` properties of the element. Initially, when the
            // element is not `.active`, its opacity is zero. After adding the
            // `to-*` class, the element is in the correct initial position.
            // Now, when adding the `active` class, CSS handles the transition
            // to move it into the middle. Note that we explicitly add the
            // `active` class later so that both class additions are processed
            // separately. Otherwise, the element could still have the opposite
            // `to-*` at the time of running this code which could make the
            // browser skip the effect of adding the correct `to-*` class. The
            // switch from, for example, `to-left` to `to-right` is fine,
            // because the element has zero opacity until we add `.active`.
            nextActiveElement.classList.remove("to-left", "to-right");
            nextActiveElement.classList.add(`to-${direction}`);
            requestAnimationFrame(() => nextActiveElement.classList.add("active"));
        }
    };
}
