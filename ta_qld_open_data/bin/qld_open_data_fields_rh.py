"""Custom admin_external REST handler backing the "Fields to ingest" live
multiselect on the Dataset input page. Given the currently-entered
portal_base_url and resource_id (passed as dependency query params by the
UCC frontend), it calls the CKAN DataStore API's datastore_search with
limit=0 to fetch the resource's field list (no rows) and returns it as
selectable options: value = raw source field id (needed to query the
`fields` param later), label = the resulting Splunk field name after
normalization, so operators see exactly what field name they'll get in
Splunk.
"""
import logging

import import_declare_test  # noqa: F401
import splunk.admin as admin
from qld_open_data_common import (
    ADDON_NAME,
    OpenDataApiError,
    OpenDataStoreClient,
    get_proxy_settings,
    normalize_field_name,
)
from solnlib import log


logger = log.Logs().get_logger(f"{ADDON_NAME.lower()}_open_data_fields")


class QldOpenDataFieldsHandler(admin.MConfigHandler):
    def setup(self):
        # Read-only listing endpoint; no create/edit/delete actions supported.
        # These must be declared as supported args or splunkd strips them from
        # self.callerArgs.data before handleList() ever sees them.
        if self.requestedAction == admin.ACTION_LIST:
            self.supportedArgs.addOptArg("portal_base_url")
            self.supportedArgs.addOptArg("resource_id")

    def handleList(self, confInfo):
        base_url = self._first(self.callerArgs.data.get("portal_base_url"))
        resource_id = self._first(self.callerArgs.data.get("resource_id"))

        if not base_url or not resource_id:
            # Nothing entered yet on the form; return an empty option list rather than erroring.
            return

        try:
            session_key = self.getSessionKey()
            proxies = get_proxy_settings(session_key, logger)
            client = OpenDataStoreClient(base_url, resource_id, proxies=proxies, logger=logger)
            fields = client.get_fields()
        except (OpenDataApiError, Exception) as exc:  # noqa: BLE001 - surface as empty list, never break the UI
            logger.warning(
                "field picker: could not fetch fields for base_url=%s resource_id=%s: %s",
                base_url, resource_id, exc,
            )
            return

        for f in fields:
            raw_id = f.get("id")
            if not raw_id:
                continue
            stanza = confInfo[raw_id]
            stanza["value"] = raw_id
            stanza["label"] = f"{normalize_field_name(raw_id)}  ({raw_id})"

    @staticmethod
    def _first(value):
        if isinstance(value, (list, tuple)):
            return value[0] if value else None
        return value


if __name__ == "__main__":
    admin.init(QldOpenDataFieldsHandler, admin.CONTEXT_NONE)
