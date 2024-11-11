#!/usr/bin/env bash

# generated using
# ./manage.py | grep -v -E "^\[|^$" | tail -n +3 | sort | xargs
COMMANDS="admin_generator anonymize changepassword check clean_pyc clear_cache clearsessions collectstatic compile_pyc compilemessages create_command create_jobs create_template_tags createcachetable createsuperuser dbshell delete_squashed_migrations describe_form diffsettings drop_test_database dump_testdata dumpdata dumpscript export_emails find_template findstatic flush format generate_password generate_secret_key graph_models inspectdb lint list_model_info list_signals loaddata loaddata_unlogged mail_debug makemessages makemigrations managestate merge_model_instances migrate notes optimizemigration pipchecker precommit print_settings print_user_for_session raise_test_exception refresh_results_cache reload_testdata remove_stale_contenttypes reset_db reset_schema run runjob runjobs runprofileserver runscript runserver runserver_plus scss send_reminders sendtestemail set_default_site set_fake_emails set_fake_passwords shell shell_plus show_template_tags show_urls showmigrations sqlcreate sqldiff sqldsn sqlflush sqlmigrate sqlsequencereset squashmigrations startapp startproject sync_s3 syncdata test testserver tools translate ts typecheck unreferenced_files update_evaluation_states update_permissions validate_templates"
TS_COMMANDS="compile test"

_managepy_complete()
{
    local cur prev
    cur=${COMP_WORDS[COMP_CWORD]}
    prev=${COMP_WORDS[COMP_CWORD-1]}

    if [ "${COMP_CWORD}" -eq 1 ]; then
        COMPREPLY=($(compgen -W "${COMMANDS}" -- "${cur}"))
    fi

    if [ "${COMP_CWORD}" -eq 2 ] && [ "${prev}" == "ts" ]; then
        COMPREPLY=($(compgen -W "${TS_COMMANDS}" -- "${cur}"))
    fi
}

complete -F _managepy_complete manage.py
