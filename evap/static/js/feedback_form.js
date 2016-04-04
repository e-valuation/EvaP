$('#feedback-form').on('submit', function(event){

    event.preventDefault();
    $('#feedback-spinner').show();

    email = $('#sender-email').val();
    message = $('#message-text').val();

    $.ajax({
        url : "/feedback/send",
        type : "POST",
        data : { sender_email : email, message: message },

        success : function(json) {
            $('#feedback-spinner').hide();
            $('#feedback-modal').modal('hide');
            $('#feedback-button').html('Message Sent!');
        }});
});
