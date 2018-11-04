$(document).ready(() => {
    var slider = $(".slider");
    var items = [];
    var index = 0;

    slider.on("transitionend", ".slider-item", event => {
        updateButtons();
        $(event.target).removeClass("to-left to-right")
            .css({top: "", height: ""});
    });

    slider.on("click", "[data-action]", event => {
        reviewAction($(event.target).data("action"));
    });
    slider.on("click", "[data-slide]", event => {
        let offset = $(event.target).data("slide") === "left" ? -1 : 1;
        slideTo(index + offset);
        updateButtons();
    });
    slider.on("click", "[data-startover]", event => {
        startOver($(event.target).data("startover"));
    });

    $(document).keydown(event => {
        let actions = {
            37: "[data-slide=left]",          // arrow left
            39: "[data-slide=right]",         // arrow right
            74: "[data-action=publish]",      // j
            75: "[data-action=make_private]", // k
            76: "[data-action=hide]",         // l
             8: "[data-action=unreview]",     // backspace
            13: "[data-url=next-course]",     // enter
            77: "[data-startover=unreviewed]",// m
            78: "[data-startover=all]"        // n
        };

        if(actions[event.which] && !event.originalEvent.repeat) {
            let element = slider.find(actions[event.which]);
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

        slider.find(".slider-side-left").toggleClass("shown", index > 0);
        let reviewed = items.slice(0, index).filter("[data-review]").length;
        slider.find("[data-counter=reviewed-left]").text(reviewed);
        slider.find("[data-counter=unreviewed-left]").text(index - reviewed);

        slider.find(".slider-side-right").toggleClass("shown", index < items.length);
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

    function startOver(action) {
        let reviewed = slider.find("[data-layer=2][data-review]");
        let unreviewed = slider.find("[data-layer=2]:not([data-review])");
        let index = action === "unreviewed" && unreviewed.length ? reviewed.length : 0;
        items = $.merge(reviewed, unreviewed);
        slideTo(index);
        updateButtons();
    }

    function reviewAction(action) {
        if(index === items.length || action === "make_private" && !items.eq(index).data("contribution")) {
            return;
        }

        let active = items.eq(index);
        let parameters = {"id": active.data("id"), "action": action, "course_id": {{ course.id }}};
        $.ajax({
            type: "POST",
            url: "{% url 'staff:course_textanswers_update_publish' %}",
            data: parameters,
            error: function(){ window.alert("{% trans 'The server is not responding.' %}"); }
        });

        if(action === "unreview") {
            active.removeAttr("data-review");
        } else {
            active.attr("data-review", action);
        }

        updateButtonActive();

        if(action !== "unreview") {
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
        slider.find("[data-action=unreview]").attr("disabled", !review);
    }
});
