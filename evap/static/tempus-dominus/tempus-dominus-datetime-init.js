document.addEventListener('DOMContentLoaded', function() {
    const pickerElement = document.getElementById('datetimepicker1');
    if (!pickerElement) {
        return;
    }

    const inputElement = pickerElement.querySelector('input');
    if (!inputElement) {
        return;
    }

    let picker;
    const createPicker = function() {
        const hasValue = inputElement.value.trim() !== '';
        let defaultDate;
        if (!hasValue) {
            defaultDate = new Date();
            defaultDate.setHours(8, 0, 0, 0);
        }

        picker = new tempusDominus.TempusDominus(pickerElement, {
            useCurrent: false,
            defaultDate,
            display: {
                theme: 'light',
                icons: {
                    time: 'fa fa-clock',
                    date: 'fa fa-calendar',
                    up: 'fa fa-arrow-up',
                    down: 'fa fa-arrow-down',
                    previous: 'fa fa-chevron-left',
                    next: 'fa fa-chevron-right',
                    today: 'fa fa-calendar-check',
                    clear: 'fa fa-trash',
                    close: 'fa fa-times'
                },
                sideBySide: true
            },
            localization: {
                format: 'yyyy-MM-dd HH:mm',
                startOfTheWeek: 1,
                hourCycle: 'h23'
            }
        });
    };

    const initializeOnFirstInteraction = function() {
        if (!picker) {
            createPicker();
            picker.show();
        }
    };

    inputElement.addEventListener('focus', initializeOnFirstInteraction, { once: true });
    pickerElement.querySelector('[data-td-toggle="datetimepicker"]')?.addEventListener('click', initializeOnFirstInteraction, { once: true });
});
