document.addEventListener("DOMContentLoaded", function () {
	const pickerElement = document.getElementById("datepicker1");
	if (!pickerElement) {
		return;
	}

	const inputElement = pickerElement.querySelector("input");
	if (!inputElement) {
		return;
	}

	const picker = new tempusDominus.TempusDominus(pickerElement, {
		display: {
			theme: "light",
			icons: {
				time: "fa fa-clock",
				date: "fa fa-calendar",
				up: "fa fa-arrow-up",
				down: "fa fa-arrow-down",
				previous: "fa fa-chevron-left",
				next: "fa fa-chevron-right",
				today: "fa fa-calendar-check",
				clear: "fa fa-trash",
				close: "fa fa-times",
			},
			components: {
				clock: false,
				hours: false,
				minutes: false,
				seconds: false,
			},
		},
		localization: {
			format: "yyyy-MM-dd",
			startOfTheWeek: 1,
			hourCycle: "h23",
		},
	});

	inputElement.addEventListener("click", function () {
		picker.show();
	});
});
