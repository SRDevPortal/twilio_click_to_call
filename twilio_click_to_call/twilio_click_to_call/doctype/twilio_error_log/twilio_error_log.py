from frappe.model.document import Document

from twilio_click_to_call.services.call_log import as_json, parse_json


class TwilioErrorLog(Document):
	def before_save(self):
		if not self.payload:
			return
		try:
			self.payload = as_json(parse_json(self.payload))
		except Exception:
			pass
