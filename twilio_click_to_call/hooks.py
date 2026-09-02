app_name = "twilio_click_to_call"
app_title = "Twilio Click To Call"
app_publisher = "SRIAAS"
app_description = "Standalone Twilio Programmable Voice integration for Frappe/ERPNext"
app_email = "webdevelopersriaas@gmail.com"
app_license = "MIT"

after_install = "twilio_click_to_call.install.after_install"
after_migrate = "twilio_click_to_call.install.after_migrate"
on_logout = "twilio_click_to_call.twilio_click_to_call.doctype.twilio_user_mapping.twilio_user_mapping.mark_user_offline_on_logout"

app_include_js = [
    "/assets/twilio_click_to_call/js/vendor/twilio.min.js",
    "/assets/twilio_click_to_call/js/softphone.js?v=20260901.1",
    "/assets/twilio_click_to_call/js/click_to_call.js",
    "/assets/twilio_click_to_call/js/list_dialer.js",
    "/assets/twilio_click_to_call/js/call_log.js",
    "/assets/twilio_click_to_call/js/availability.js?v=20260831.2",
]

doctype_js = {
    "Twilio Settings": "public/js/twilio_settings.js",
    "Twilio User Mapping": "public/js/twilio_user_mapping.js",
}

doctype_list_js = {
    "Twilio User Mapping": "public/js/twilio_user_mapping_list.js",
}

permission_query_conditions = {
    "Twilio Call Log": "twilio_click_to_call.api.permissions.get_permission_query_conditions",
    "Twilio Error Log": "twilio_click_to_call.api.permissions.get_error_permission_query_conditions",
}

has_permission = {
    "Twilio Call Log": "twilio_click_to_call.api.permissions.has_call_log_permission",
    "Twilio Error Log": "twilio_click_to_call.api.permissions.has_error_log_permission",
}

doc_events = {
    "Issue": {
        "on_trash": "twilio_click_to_call.services.delete_cleanup.cleanup_issue_call_log_links",
    },
    "Twilio Call Log": {
        "on_trash": "twilio_click_to_call.services.delete_cleanup.cleanup_call_log_reverse_links",
        "on_update": [
            "twilio_click_to_call.services.ai.on_twilio_call_log_update",
            "twilio_click_to_call.services.realtime.publish_call_disconnected",
        ],
    },
}

scheduler_events = {
    "cron": {
        "* * * * *": [
            "twilio_click_to_call.services.cdr.recover_stale_ringing_calls",
        ],
    },
    "hourly": [
        "twilio_click_to_call.services.cdr.enqueue_recent_cdr_sync",
        "twilio_click_to_call.services.cdr.enqueue_missing_inbound_cdr_sync",
        "twilio_click_to_call.api.console.close_stale_agent_attendance_sessions",
    ],
}
