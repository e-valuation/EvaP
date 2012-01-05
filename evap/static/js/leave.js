// Create a variable that can be set upon form submission
var submitFormOkay = false;

(function($) {
	$(window).bind('beforeunload', function(){
		if (!submitFormOkay) {
			return 'Are you sure you want to leave?';
		}
	});
})( jQuery );