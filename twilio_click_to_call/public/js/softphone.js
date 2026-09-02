(function(){if(window.dev_server&&window.frappe&&frappe.realtime&&/\.ngrok-(free\.)?dev$|\.ngrok\.io$|\.ngrok\.app$/i.test(window.location.hostname)){frappe.realtime.get_host=function(){return window.location.origin+'/'+frappe.boot.sitename;};}})();(function () {
    "use strict";

    let device = null;
    let activeCall = null;
    let tokenRequest = null;

    function fetchToken() {
        if (tokenRequest) return tokenRequest;
        tokenRequest = Promise.resolve(frappe.call({
            method: "twilio_click_to_call.api.device.get_token",
            // Token registration runs in the background on every Desk page.
            // Unmapped users are expected (for example, Administrator), so let
            // the caller decide whether an error should be surfaced.
            silent: true,
        })).then((r) => r.message || {}).finally(() => {
            tokenRequest = null;
        });
        return tokenRequest;
    }

    async function ensureDevice(register = true) {
        if (!window.Twilio || !window.Twilio.Device) {
            throw new Error(__("Twilio Voice SDK did not load."));
        }
        if (!device) {
            const credentials = await fetchToken();
            device = new window.Twilio.Device(credentials.token, {
                closeProtection: true,
                codecPreferences: ["opus", "pcmu"],
                logLevel: 1,
            });
            bindDeviceEvents(device);
        }
        if (register && device.state !== "registered") {
            await device.register();
        }
        return device;
    }

    function bindDeviceEvents(currentDevice) {
        currentDevice.on("registered", () => {
            $(document).trigger("twilio_softphone_registered");
        });
        currentDevice.on("unregistered", () => {
            $(document).trigger("twilio_softphone_unregistered");
        });
        currentDevice.on("error", (error) => {
            console.error("Twilio Voice SDK", error);
            frappe.show_alert({
                message: error.message || __("Twilio softphone error."),
                indicator: "red",
            }, 8);
        });
        currentDevice.on("tokenWillExpire", async () => {
            try {
                const credentials = await fetchToken();
                currentDevice.updateToken(credentials.token);
            } catch (error) {
                console.error("Could not refresh Twilio token", error);
            }
        });
        currentDevice.on("incoming", (call) => {
            const from = (call.parameters && call.parameters.From) ||
                (call.customParameters && call.customParameters.get("from")) ||
                __("Unknown caller");
            frappe.confirm(
                __("Incoming call from {0}. Answer?", [frappe.utils.escape_html(from)]),
                () => {
                    setActiveCall(call);
                    call.accept();
                },
                () => call.reject()
            );
        });
    }

    function setActiveCall(call) {
        activeCall = call;
        const finish = () => {
            if (activeCall === call) activeCall = null;
            $(document).trigger("twilio_refresh_availability");
            $(document).trigger("twilio_softphone_call_ended");
        };
        call.on("accept", () => $(document).trigger("twilio_softphone_call_accepted", [call]));
        call.on("disconnect", finish);
        call.on("cancel", finish);
        call.on("reject", finish);
        call.on("error", (error) => {
            frappe.show_alert({message: error.message || __("Twilio call failed."), indicator: "red"}, 8);
            finish();
        });
    }

    async function startOutbound(message) {
        const params = (message || {}).connect_params;
        if (!params || !params.call_log || !params.token) {
            throw new Error(__("The server did not return Twilio connection parameters."));
        }
        if (activeCall) {
            throw new Error(__("A softphone call is already active."));
        }
        const currentDevice = await ensureDevice(true);
        const call = await currentDevice.connect({params});
        setActiveCall(call);
        $(document).trigger("twilio_softphone_call_started", [message, call]);
        return call;
    }

    function disconnect() {
        if (activeCall) activeCall.disconnect();
    }

    function mute(value) {
        if (activeCall) activeCall.mute(Boolean(value));
    }

    window.twilio_softphone = {
        initialize: ensureDevice,
        startOutbound,
        disconnect,
        mute,
        get device() { return device; },
        get activeCall() { return activeCall; },
    };

    $(function () {
        if (!window.frappe || !frappe.session || frappe.session.user === "Guest") return;
        ensureDevice(true).catch(() => {
            // Disabled or unmapped users should not see startup noise.
        });
    });
})();
