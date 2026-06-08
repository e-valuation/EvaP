import { tempusDominus } from "./tempus-dominus.js";

document.addEventListener("DOMContentLoaded", () => {
    const pickerElements = document.querySelectorAll<HTMLElement>("[id^='datetimepicker']");
    pickerElements.forEach(pickerElement => {
        const inputElement = pickerElement.querySelector("input");
        if (!inputElement) {
            return;
        }

        const toggleElement = pickerElement.querySelector("[data-td-toggle]");
        if (!toggleElement) {
            return;
        }

        let picker: any = null;

        const createPicker = (): void => {
            const hasValue = inputElement.value.trim() !== "";
            let defaultDate: Date | undefined;
            if (!hasValue) {
                defaultDate = new Date();
                defaultDate.setHours(8, 0, 0, 0);
            }

            picker = new tempusDominus.TempusDominus(pickerElement, {
                useCurrent: false,
                defaultDate,
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
                    sideBySide: true,
                },
                localization: {
                    format: "yyyy-MM-dd HH:mm",
                    startOfTheWeek: 1,
                    hourCycle: "h23",
                },
            });
        };

        const openPicker = (): void => {
            if (!picker) {
                createPicker();
            }
            picker.show();
        };

        inputElement.addEventListener("click", openPicker);
    });
});
