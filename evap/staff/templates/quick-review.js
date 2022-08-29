// TODO: DELETE ME

// Limits `val` to the interval [lowest, highest] - both ends included.
const clamp = (val, lowest, highest) => Math.min(highest, Math.max(lowest, val));

$(document).ready(() => {
    const slider = $(".slider");
    let answerSlides = [];
    let selectedIndex = 0;

    const endSlideSelected = () => selectedIndex === answerSlides.length;

    startOver("undecided");

    const updateForm = document.getElementById("textanswer-update-form");
    updateForm.addEventListener("submit", event => {
        const actionButton = event.submitter;
        if (
            endSlideSelected()
            || (actionButton.getAttribute("value") === "make_private"
                && !("contribution" in answerSlides[selectedIndex].dataset))
        ) {
            event.preventDefault();
        } else {
            // Update UI after submit is done (https://stackoverflow.com/q/71473512/13679671)
            setTimeout(() => reviewAction(actionButton.getAttribute("value")));
        }
    });

    slider.on("transitionend", ".slider-item", event => {
        updateButtons();
        $(event.target).removeClass("to-left to-right")
            .css({ top: "", height: "" });
    });

    slider.on("click", "[data-slide]", event => {
        const offset = $(event.target).data("slide") === "left" ? -1 : 1;
        slideTo(selectedIndex + offset);
        updateButtons();
    });
    slider.on("click", "[data-startover]", event => {
        startOver($(event.target).data("startover"));
    });

    $(document).keydown(event => {
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            return;
        }

        const actions = {
            "arrowleft": "[data-slide=left]",
            "arrowright": "[data-slide=right]",
            "j": "[type=submit][name=action][value=publish]",
            "k": "[type=submit][name=action][value=make_private]",
            "l": "[type=submit][name=action][value=delete]",
            "backspace": "[type=submit][name=action][value=unreview]",
            "e": "[type=submit][name=action][value=textanswer_edit]",
            "enter": `[data-url=next-evaluation][data-next-evaluation-index="${nextEvaluationIndex}"]`,
            "m": "[data-startover=undecided]",
            "n": "[data-startover=all]",
            "s": "[data-skip-evaluation]",
        };
        const action = actions[event.key.toLowerCase()];

        if (action && !event.originalEvent.repeat) {
            slider[0].querySelector(action)?.click();
            event.preventDefault();
        }
    });

    function slideTo(requestedIndex) {
        requestedIndex = clamp(requestedIndex, 0, answerSlides.length);
        const direction = requestedIndex >= selectedIndex ? "right" : "left";
        selectedIndex = requestedIndex;

        if (endSlideSelected()) {
            const slidesExist = answerSlides.length !== 0;
            const allReviewed = answerSlides.filter(":not([data-review])").length === 0;
            const alertSlide = slider.find(".alert");
            alertSlide.toggleClass("alert-warning", !allReviewed);
            alertSlide.toggleClass("alert-success", allReviewed && slidesExist);
            alertSlide.toggleClass("alert-secondary", allReviewed && !slidesExist);
            alertSlide.find("[data-content=unreviewed]").toggleClass("d-none", allReviewed);
            alertSlide.find("[data-content=reviewed]").toggleClass("d-none", !allReviewed);
            slider.find("[data-startover=undecided]").toggleClass("d-none", allReviewed);
            slider.find("[data-startover=all]").toggleClass("d-none", !slidesExist);
            slideLayer(2, direction, alertSlide);
        } else {
            slideLayer(2, direction, answerSlides.eq(selectedIndex));
            const newAnswerId = answerSlides[selectedIndex].dataset.id;
            slider[0].querySelectorAll("input[name=answer_id]").forEach((input) => input.disabled = input.value !== newAnswerId);
        }

        slider.find(".slider-side-left").toggleClass("visible", selectedIndex > 0);
        let reviewed = answerSlides.slice(0, selectedIndex).filter("[data-review]").length;
        slider.find("[data-counter=reviewed-left]").text(reviewed);
        slider.find("[data-counter=unreviewed-left]").text(selectedIndex - reviewed);
        slider.find(".slider-side-right").toggleClass("visible", selectedIndex < answerSlides.length);
        reviewed = answerSlides.slice(selectedIndex + 1).filter("[data-review]").length;
        slider.find("[data-counter=reviewed-right]").text(reviewed);
        const unreviewed = answerSlides.length - selectedIndex - reviewed - 1;
        slider.find("[data-counter=unreviewed-right]").text(Math.max(unreviewed, 0));
    }

    function slideLayer(layer, direction, element) {
        // to preserve the vertical positions and heights during transition,
        // the elements will be deactivated from bottom to top and activated from top to bottom

        if (element?.is(".active")) {
            return;
        }

        const last = slider.find("[data-layer=" + layer + "].active, .alert.active");
        if (last.length !== 0) {
            const reversed = direction === "left" ? "right" : "left";
            last.css({ top: last.position().top, height: last.outerHeight() });
            last.removeClass("active to-left to-right");
            last.addClass("to-" + reversed);
        }

        if (layer > 0) {
            if (selectedIndex < answerSlides.length) {
                const reference = element.prevAll("[data-layer=" + (layer - 1) + "]").first();
                slideLayer(layer - 1, direction, reference);
            } else {
                slideLayer(layer - 1, direction, null);
            }
        }

        if (element !== null) {
            element.removeClass("to-left to-right");
            element.position();
            element.addClass("to-" + direction);
            element.position();
            element.addClass("active");
        }
    }

    let nextEvaluationIndex = 0;
    updateNextEvaluation(0);

    $("[data-skip-evaluation]").on("click", event => {
        const skippedEvaluationId = $("[data-evaluation]").not(":hidden").data("evaluation");
        if (skippedEvaluationId !== undefined) {
            $.ajax({
                type: "POST",
                data: { evaluation_id: skippedEvaluationId },
                url: "{% url 'staff:evaluation_textanswers_skip' %}",
                error: function() { window.alert("{% trans 'The server is not responding.' %}"); }
            });
            updateNextEvaluation(++nextEvaluationIndex);
        }
    });

    function updateNextEvaluation(index) {
        let nextEvaluation = false;
        $("[data-next-evaluation-index]").each(function() {
            if ($(this).data("next-evaluation-index") == index) {
                $(this).show();
                nextEvaluation = true;
            } else {
                $(this).hide();
            }
        });
        if (!nextEvaluation) {
            $("[data-skip-evaluation]").hide();
        }
    }

    function startOver(action) {
        const reviewed = slider.find("[data-layer=2][data-review]");
        const unreviewed = slider.find("[data-layer=2]:not([data-review])");
        const startIndex = action === "undecided" && unreviewed.length > 0 ? reviewed.length : 0;
        answerSlides = $.merge(reviewed, unreviewed);
        slideTo(startIndex);
        updateButtons();
    }

    function reviewAction(action) {
        const active = answerSlides.eq(selectedIndex);

        if (action === "unreview") {
            active.removeAttr("data-review");
            updateButtons();
        } else {
            active.attr("data-review", action);
            updateButtonActive();
        }

        if (!["unreview", "textanswer_edit"].includes(action)) {
            slideTo(selectedIndex + 1);
            slider.find(`[type=submit][name=value][value=${action}]`).focus();
        }
    }

    function updateButtons() {
        slider.find("[data-action-set=reviewing]").toggleClass("d-none", selectedIndex === answerSlides.length);
        slider.find("[data-action-set=summary]").toggleClass("d-none", selectedIndex < answerSlides.length);

        if (selectedIndex < answerSlides.length) {
            updateButtonActive();
            const notContributor = !answerSlides.eq(selectedIndex).data("contribution");
            const privateBtn = slider.find("[type=submit][name=action][value=make_private]");
            privateBtn.attr("disabled", notContributor);
            privateBtn.tooltip(notContributor ? 'enable' : 'disable');

            const review = answerSlides.eq(selectedIndex).attr("data-review");
            slider.find("[type=submit][name=action][value=unreview]").attr("disabled", !review);
        }
    }

    function updateButtonActive() {
        const active = answerSlides.eq(selectedIndex);
        // focus the answer to enable scrolling with arrow keys
        active.focus();
        slider.find(".btn:focus").blur();

        const actions = {
            publish: "btn-success",
            make_private: "btn-dark",
            delete: "btn-danger"
        };

        const review = active.attr("data-review");
        for (const action in actions) {
            const btn = slider[0].querySelector(`[type=submit][name=action][value=${action}]`);
            btn.classList.toggle(actions[action], review === action);
            btn.classList.toggle("btn-outline-secondary", review !== action);
        }
    }
});
