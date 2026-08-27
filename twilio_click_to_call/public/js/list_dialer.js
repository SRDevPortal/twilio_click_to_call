(function () {
    const DEFAULT_DOCTYPES = ["CRM Lead", "Contact", "Patient", "Customer"];
    const registeredDoctypes = new Set();
    let installed = false;

    function currentRoute() {
        if (!window.frappe || !frappe.get_route) return [];
        return frappe.get_route() || [];
    }

    function isDeskHome() {
        return window.location && window.location.pathname === "/app/home";
    }

    function shouldInstall() {
        if (isDeskHome()) return false;
        const route = currentRoute();
        return route[0] === "List";
    }

    function install() {
        if (!window.frappe) return;
        if (installed || !shouldInstall()) return;
        frappe.listview_settings = frappe.listview_settings || {};

        loadAllowedDoctypes((doctypes) => {
            doctypes.forEach(registerListDialer);
            installed = true;
        });
    }

    function registerListDialer(doctype) {
        if (!doctype || registeredDoctypes.has(doctype)) return;
        registeredDoctypes.add(doctype);

            const existing = frappe.listview_settings[doctype] || {};
            if (existing.__twilio_extended) return;

            const originalOnload = existing.onload;
            existing.onload = function (listview) {
                if (typeof originalOnload === "function") {
                    originalOnload.call(this, listview);
                }
                addListDialer(listview, doctype);
            };
            existing.__twilio_extended = true;
            frappe.listview_settings[doctype] = existing;
    }

    function loadAllowedDoctypes(callback) {
        if (!frappe.session || frappe.session.user === "Guest") {
            callback(DEFAULT_DOCTYPES);
            return;
        }

        frappe.call({
            method: "twilio_click_to_call.api.call.get_allowed_doctypes_api",
        }).then((r) => {
            callback(Array.isArray(r.message) && r.message.length ? r.message : DEFAULT_DOCTYPES);
        });
    }

    function addListDialer(listview, doctype) {
        if (!listview || !listview.page || listview.__twilio_list_dialer) return;
        listview.__twilio_list_dialer = true;

        listview.page.add_inner_button(__("Twilio Call Selected"), () => {
            const selected = getSelected(listview);
            if (!selected.length) {
                frappe.msgprint(__("Select one record to call."));
                return;
            }
            callFromList(doctype, selected[0].name);
        });
    }

    function getSelected(listview) {
        if (typeof listview.get_checked_items === "function") {
            return listview.get_checked_items() || [];
        }
        return [];
    }

    function callFromList(doctype, name) {
        frappe.confirm(__("Start Twilio call for {0}?", [frappe.utils.escape_html(name)]), () => {
            frappe.call({
                method: "twilio_click_to_call.api.call.start_call",
                args: {
                    reference_doctype: doctype,
                    reference_name: name,
                },
                freeze: true,
                freeze_message: __("Starting call..."),
            }).then((r) => {
                const message = r.message || {};
                if (message.connect_params && window.twilio_softphone) {
                    window.twilio_softphone.startOutbound(message).catch((error) => {
                        frappe.msgprint(error.message || __("Could not start the Twilio softphone call."));
                    });
                }
                $(document).trigger("twilio_refresh_availability");
                $(document).trigger("twilio_list_call_started", [message.call_log]);
                frappe.show_alert({
                    message: __("Call started: {0}", [message.call_log || "Twilio"]),
                    indicator: "green",
                });
            });
        });
    }

    $(install);
    $(document).on("page-change route-change", install);
})();
