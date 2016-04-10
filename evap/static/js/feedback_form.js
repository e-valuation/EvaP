$('#feedback-form').on('submit', function(event){

    event.preventDefault();
    $('#feedback-spinner').show();

    message = $('#message-text').val();

    $.ajax({
        url : "/feedback/send",
        type : "POST",
        data : { message: message },

        success : function(json) {
            $('#feedback-spinner').hide();
            $('#feedback-modal').modal('hide');
            var text = $('#feedback-button button').html();
            $('#feedback-button button').html('Message sent.');
            setTimeout(function(){
                $('#feedback-button button').html(text);
            }, 3000);
        }});
});
