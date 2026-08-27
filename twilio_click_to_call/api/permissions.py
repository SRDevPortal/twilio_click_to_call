from __future__ import annotations

import frappe


def _is_system_manager(user: str) -> bool:
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def get_permission_query_conditions(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if _is_system_manager(user):
        return None
    return f"`tabTwilio Call Log`.`user` = {frappe.db.escape(user)}"


def has_call_log_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    user = user or frappe.session.user
    if _is_system_manager(user):
        return True
    return permission_type in (None, "read", "print", "email", "export") and doc.user == user


def get_error_permission_query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    return "" if _is_system_manager(user) else "1=0"


def has_error_log_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    return _is_system_manager(user or frappe.session.user)


# Backward-compatible local names used by older reports.
call_log_query = get_permission_query_conditions
call_log_has_permission = has_call_log_permission
