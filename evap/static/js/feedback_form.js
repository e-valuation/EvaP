$('#feedback_form').on('submit', function(event){

    event.preventDefault();
    $('#feedback_spinner').show();

    email = $('#sender_email').val();
    message = $('#message_text').val();

    $.ajax({
        url : "/feedback/create",
        type : "POST",
        data : { sender_email : email, message: message },

        success : function(json) {
            $('#feedback_spinner').hide();
            $('#feedback_modal').modal('hide');
            $('#feedback_button').html('Message Sent!');
        }});
});