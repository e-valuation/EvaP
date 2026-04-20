document.addEventListener('DOMContentLoaded', function() {
    const picker = new tempusDominus.TempusDominus(document.getElementById('datepicker1'), {
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
            components: {
                clock: false,   // Hides the clock toggle button
                hours: false,   // Hides the hour picker
                minutes: false, // Hides the minute picker
                seconds: false  // (Already false by default, but good to ensure)
            },
        },
        localization: {
            format: 'yyyy-MM-dd',
            startOfTheWeek: 1,
            hourCycle: 'h23'
        }
    });
});
