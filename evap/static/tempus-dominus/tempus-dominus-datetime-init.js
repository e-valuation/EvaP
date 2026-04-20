document.addEventListener('DOMContentLoaded', function() {
    const picker = new tempusDominus.TempusDominus(document.getElementById('datetimepicker1'), {
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
});
