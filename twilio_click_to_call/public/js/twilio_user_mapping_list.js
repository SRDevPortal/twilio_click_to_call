frappe.listview_settings['Twilio User Mapping'] = {
	onload() {
		frappe.call({
			method: 'twilio_click_to_call.twilio_click_to_call.doctype.twilio_settings.twilio_settings.get_caller_id_options',
		}).then((r) => {
			const callerIdField = frappe.meta.get_docfield('Twilio User Mapping', 'caller_id');
			if (!callerIdField) return;

			callerIdField.options = [''].concat(r.message || []).join('\n');
		});
	},
};
