$(document).ready(() => {
    var slider = $(".slider");
    var items = [];
    var index = 0;

    slider.on("transitionend", ".slider-item", event => {
        updateButtons();
        $(event.target).removeClass("to-left to-right")
            .css({top: "", height: ""});
    });

    for (const actionButton of slider[0].querySelectorAll("[data-action]")) {
        actionButton.addEventListener("click", () => {
            reviewAction(actionButton.dataset.action);
        });
    }

    slider.on("click", "[data-slide]", event => {
        let offset = $(event.target).data("slide") === "left" ? -1 : 1;
        slideTo(index + offset);
        updateButtons();
    });
    slider.on("click", "[data-startover]", event => {
        startOver($(event.target).data("startover"));
    });

    $(document).keydown(event => {
        const actions = {
            "arrowleft":    "[data-slide=left]",
            "arrowright":   "[data-slide=right]",
            "j":            "[data-action=publish]",
            "k":            "[data-action=make_private]",
            "l":            "[data-action=hide]",
            "backspace":    "[data-action=unreview]",
            "e":            "[data-action=textanswer_edit]",
            "enter":        `[data-url=next-evaluation][data-next-evaluation-index=${nextEvaluationIndex}]`,
            "m":            "[data-startover=unreviewed]",
            "n":            "[data-startover=all]",
            "s":            "[data-skip-evaluation]",
        };
        const action = actions[event.key.toLowerCase()];

        if(action && !event.originalEvent.repeat) {
            let element = slider.find(action);
            if(element.length) {
                element[0].click();
            }
            event.preventDefault();
        }
    });

    startOver("unreviewed");

    function slideTo(requestedIndex) {
        requestedIndex = Math.min(Math.max(requestedIndex, 0), items.length);
        let direction = requestedIndex >= index ? "right" : "left";
        index = requestedIndex;

        if(index === items.length) {
            let reviewed = items.filter(":not([data-review])").length === 0;
            let alert = slider.find(".alert");
            alert.toggleClass("alert-warning", !reviewed);
            alert.toggleClass("alert-success", reviewed && items.length !== 0);
            alert.toggleClass("alert-secondary", reviewed && items.length === 0);
            alert.find("[data-content=unreviewed]").toggleClass("d-none", reviewed);
            alert.find("[data-content=reviewed]").toggleClass("d-none", !reviewed);
            slider.find("[data-action=startover-unreviewed]").toggleClass("d-none", reviewed);
            slider.find("[data-action=startover-all]").toggleClass("d-none", items.length === 0);
            slideLayer(2, direction, alert);
        } else {
            slideLayer(2, direction, items.eq(index));
        }

        slider.find(".slider-side-left").toggleClass("visible", index > 0);
        let reviewed = items.slice(0, index).filter("[data-review]").length;
        slider.find("[data-counter=reviewed-left]").text(reviewed);
        slider.find("[data-counter=unreviewed-left]").text(index - reviewed);

        slider.find(".slider-side-right").toggleClass("visible", index < items.length);
        reviewed = items.slice(index + 1).filter("[data-review]").length;
        slider.find("[data-counter=reviewed-right]").text(reviewed);
        let unreviewed = items.length - index - reviewed - 1;
        slider.find("[data-counter=unreviewed-right]").text(Math.max(unreviewed, 0));
    }

    function slideLayer(layer, direction, element) {
        // to preserve the vertical positions and heights during transition,
        // the elements will be deactivated from bottom to top and activated from top to bottom

        if(element && element.is(".active")) {
            return;
        }

        let last = slider.find("[data-layer=" + layer + "].active, .alert.active");
        if(last.length !== 0) {
            let reversed = direction === "left" ? "right" : "left";
            last.css({top: last.position().top, height: last.outerHeight()});
            last.removeClass("active to-left to-right");
            last.addClass("to-" + reversed);
        }

        if(layer > 0) {
            if(index < items.length) {
                let reference = element.prevAll("[data-layer=" + (layer - 1) + "]").first();
                slideLayer(layer - 1, direction, reference);
            } else {
                slideLayer(layer - 1, direction, null);
            }
        }

        if(element !== null) {
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
                data: {evaluation_id: skippedEvaluationId},
                url: "{% url 'staff:evaluation_textanswers_skip' %}",
                error: function(){ window.alert("{% trans 'The server is not responding.' %}"); }
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
        let reviewed = slider.find("[data-layer=2][data-review]");
        let unreviewed = slider.find("[data-layer=2]:not([data-review])");
        let index = action === "unreviewed" && unreviewed.length ? reviewed.length : 0;
        items = $.merge(reviewed, unreviewed);
        slideTo(index);
        updateButtons();
    }

    function reviewAction(action) {
        if(!action || index === items.length || action === "make_private" && !items.eq(index).data("contribution")) {
            return;
        }

        let active = items.eq(index);
        let parameters = {"id": active.data("id"), "action": action, "evaluation_id": {{ evaluation.id }}};
        $.ajax({
            type: "POST",
            url: "{% url 'staff:evaluation_textanswers_update_publish' %}",
            data: parameters,
            success: function(data) { if(action == "textanswer_edit" && data) window.location = data; },
            error: function(){ window.alert("{% trans 'The server is not responding.' %}"); }
        });

        if(action === "unreview") {
            active.removeAttr("data-review");
            updateButtons();
        } else {
            active.attr("data-review", action);
            updateButtonActive();
        }

        if(!["unreview", "textanswer_edit"].includes(action)) {
            slideTo(index + 1);
            slider.find("[data-action=" + action + "]").focus();
        }
    }

    function updateButtons() {
        slider.find("[data-action-set=reviewing]").toggleClass("d-none", index === items.length);
        slider.find("[data-action-set=summary]").toggleClass("d-none", index < items.length);

        if(index < items.length) {
            updateButtonActive();
            let notContributor = !items.eq(index).data("contribution");
            let privateBtn = slider.find("[data-action=make_private]");
            privateBtn.attr("disabled", notContributor);
            privateBtn.tooltip(notContributor ? 'enable' : 'disable');

            let review = items.eq(index).attr("data-review");
            slider.find("[data-action=unreview]").attr("disabled", !review);
        }
    }

    function updateButtonActive() {
        let active = items.eq(index);
        // focus the answer to enable scrolling with arrow keys
        active.focus();
        slider.find(".btn:focus").blur();

        let actions = {
            publish: "btn-success",
            make_private: "btn-dark",
            hide: "btn-danger"
        };

        let review = active.attr("data-review");
        for(let action in actions) {
            let btn = slider.find("[data-action=" + action + "]");
            btn.toggleClass(actions[action], review === action);
            btn.toggleClass("btn-outline-secondary", review !== action);
        }
    }
});
