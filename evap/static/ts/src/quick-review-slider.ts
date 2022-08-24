import { selectOrError, clamp } from "./utils";

type Slide = HTMLElement;
type SlideDirection = "left" | "right";
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

class QuickReviewSlider {
    slider: HTMLElement;
    sliderItems: Array<HTMLElement>;
    slideTriggers: Array<HTMLElement>;

    answerSlides: Array<Slide> = [];
    alertSlide: HTMLElement;
    alertContentSpans: { unreviewed: HTMLElement, reviewed: HTMLElement };
    startOverTriggers: { undecided: HTMLElement, all: HTMLElement };

    navigationButtons: { left: NavigationButtonWithCounters, right: NavigationButtonWithCounters };

    updateForm: HTMLFormElement;

    selectedSlideIndex: number = 0;
    nextEvaluationIndex: number = 0;

    constructor(slider: HTMLElement, updateForm: HTMLFormElement) {
        this.slider = slider;
        this.updateForm = updateForm;
        this.sliderItems = Array.from(this.slider.querySelectorAll(".slider-item"));
        this.slideTriggers = Array.from(this.slider.querySelectorAll("[data-slide]"));
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
        }
    }

    //
    // State
    //
    isShowingEndslide() { return this.selectedSlideIndex === this.answerSlides.length; }
    get selectedSlide() { return this.answerSlides[this.selectedSlideIndex]; }

    //
    // DOM
    //
    attach() {
        this.updateForm.addEventListener("submit", this.formSubmitHandler);
        document.addEventListener("keydown", this.keydownHandler);
        const skipEvaluationButton = selectOrError("[data-skip-evalaution]");
        skipEvaluationButton.addEventListener("click", this.skipEvaluationHandler);
        this.sliderItems.forEach(item => item.addEventListener("transitionend", () => {
            this.updateButtons();
            item.classList.remove("to-left", "to-right");
            item.style.top = "";
            item.style.height = "";
        }));
        this.slideTriggers.forEach(trigger => trigger.addEventListener("click", () => {
            const offset = trigger.dataset.slide === "left" ? - 1 : 1;
            this.slideTo(this.selectedSlideIndex + offset);
            this.updateButtons();
        }));

        this.startOver(StartOverWhere.Undecided);
        this.updateNextEvaluation();
    }

    formSubmitHandler(event: SubmitEvent) {
        const actionButton = event.submitter!;
        if (this.isShowingEndslide() || this.isWrongSubmit(actionButton)) {
            event.preventDefault();
            return;
        }

        // Update UI after submit is done (https://stackoverflow.com/q/71473512/13679671)
        setTimeout(() => this.reviewAction(actionButton.getAttribute("value")!));
    }
    keydownHandler(event: KeyboardEvent) {
        // TODO 
    }
    skipEvaluationHandler(event: Event) { }
    reviewAction(action: Action) { }

    isWrongSubmit(submitter: HTMLElement) { return submitter.getAttribute("value") === "make_private" && !("contribution" in this.selectedSlide.dataset); }

    //
    // UI Updates
    //
    updateButtons() { }
    updateButtonsActive() { }
    updateNextEvaluation() { }
    updateAnswerIdInputs() {
        const newAnswerId = this.selectedSlide.dataset.id;
        for (const input of this.slider.querySelectorAll<HTMLInputElement>("input[name=answer_id]")) {
            input.disabled = input.value !== newAnswerId;
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
        this.navigationButtons.right.unreviewedCounter.innerText = Math.max(rightSlides.length - rightReviewed, 0).toString();
    }

    //
    // Sliding
    //
    startOver(where: StartOverWhere) { }
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
    slideLayer(layer: Layer, direction: SlideDirection, element: HTMLElement) { }
}

