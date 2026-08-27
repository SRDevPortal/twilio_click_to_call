frappe.ui.form.on("Twilio Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Sync Twilio Configuration"), () => {
            frappe.call({
                method: "twilio_click_to_call.api.provisioning.sync_twilio_configuration",
                freeze: true,
                freeze_message: __("Configuring Twilio..."),
            }).then((r) => {
                const data = r.message || {};
                frm.set_value("twiml_application_sid", data.application_sid || "");
                frm.save();
                frappe.msgprint(
                    __("Twilio configuration synced. Numbers updated: {0}", [
                        (data.synced_numbers || []).length,
                    ])
                );
            });
        });

        frm.add_custom_button(__("Sync AI Dispositions"), () => {
            frappe.call({
                method: "twilio_click_to_call.twilio_click_to_call.doctype.twilio_settings.twilio_settings.sync_ai_disposition_options",
                freeze: true,
                freeze_message: __("Syncing SR Lead Disposition records..."),
            }).then((r) => {
                const data = r.message || {};
                frm.set_value("ai_disposition_options", data.options || "");
                frm.refresh_field("ai_disposition_options");
                frappe.show_alert({
                    message: __("Synced {0} AI disposition options", [data.count || 0]),
                    indicator: "green",
                });
            });
        });
    },
});
