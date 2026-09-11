"""Shared client for the CKAN DataStore API (the technology behind the
Queensland Government Open Data portal), plus proxy/conf helpers and
Splunk field-name normalization. Used by both the modular input
(qld_open_data_helper.py) and the live field-picker REST handler
(qld_open_data_fields_rh.py).
"""
import logging
import re
import time
from urllib.parse import quote

import import_declare_test  # noqa: F401
import requests
from solnlib import conf_manager


ADDON_NAME = "ta_qld_open_data"
DEFAULT_PAGE_SIZE = 1000
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60

_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def normalize_field_name(raw_name: str) -> str:
    """Convert a raw CKAN DataStore field id into a Splunk-friendly field name:
    lowercase, ASCII alphanumeric + underscore only, cannot start with a digit,
    no leading/trailing/duplicate underscores. CKAN's synthetic row identifier
    `_id` is renamed to `ckan_id` so it isn't hidden by Splunk's convention of
    hiding underscore-prefixed fields.
    """
    if raw_name is None:
        return "field"
    name = raw_name.strip()
    if name == "_id":
        return "ckan_id"
    name = name.lower()
    name = _INVALID_CHARS.sub("_", name).strip("_")
    if not name:
        return "field"
    if name[0].isdigit():
        name = f"f_{name}"
    return name


def normalize_record_keys(record: dict) -> dict:
    """Normalize every key in a CKAN record dict, de-duplicating collisions
    (e.g. two source fields that normalize to the same name) with a numeric
    suffix so no data is silently dropped."""
    normalized = {}
    seen_counts = {}
    for raw_key, value in record.items():
        key = normalize_field_name(raw_key)
        if key in seen_counts:
            seen_counts[key] += 1
            key = f"{key}_{seen_counts[key]}"
        else:
            seen_counts[key] = 1
        normalized[key] = value
    return normalized


def get_conf(session_key: str, conf_name: str):
    cfm = conf_manager.ConfManager(
        session_key,
        ADDON_NAME,
        realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-{conf_name}",
    )
    return cfm.get_conf(conf_name)


def get_proxy_settings(session_key: str, logger: logging.Logger = None):
    """Build a requests-style proxies dict from the TA's proxy stanza, honoring proxy_enabled."""
    try:
        settings_conf = get_conf(session_key, f"{ADDON_NAME}_settings")
        stanza = settings_conf.get("proxy")
    except Exception:
        if logger:
            logger.debug("No proxy stanza configured; proceeding without a proxy.")
        return None

    if stanza.get("proxy_enabled") not in ("1", 1, "true", "True", True):
        return None

    ptype = stanza.get("proxy_type", "http")
    if ptype == "socks5" and stanza.get("proxy_rdns") in ("1", "true", "True", True):
        ptype = "socks5h"

    auth = ""
    proxy_username = stanza.get("proxy_username")
    if proxy_username:
        proxy_password = stanza.get("proxy_password", "")
        auth = f"{quote(proxy_username, safe='')}:{quote(proxy_password, safe='')}@"

    url = f"{ptype}://{auth}{stanza['proxy_url']}:{stanza['proxy_port']}"
    return {"http": url, "https": url}


class OpenDataApiError(Exception):
    pass


class OpenDataStoreClient:
    """Minimal, resilient client for the public CKAN DataStore `datastore_search` action.
    Works against any CKAN portal/resource_id, not just a specific dataset."""

    def __init__(self, base_url: str, resource_id: str, proxies=None, logger: logging.Logger = None):
        self.base_url = base_url.rstrip("/")
        self.resource_id = resource_id
        self.proxies = proxies
        self.logger = logger
        self.session = requests.Session()

    def _get(self, params: dict, max_retries: int = 5) -> dict:
        url = f"{self.base_url}/api/3/action/datastore_search"
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    proxies=self.proxies,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )
            except requests.RequestException as exc:
                wait = min(2 ** attempt, 60)
                if self.logger:
                    self.logger.warning(
                        "attempt=%d transient error contacting CKAN DataStore: %s; retrying in %ss",
                        attempt, exc, wait,
                    )
                time.sleep(wait)
                continue

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", min(2 ** attempt, 60)))
                if self.logger:
                    self.logger.warning("429 rate limited by CKAN, sleeping %ss", wait)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                wait = min(2 ** attempt, 60)
                if self.logger:
                    self.logger.warning(
                        "server error %s from CKAN DataStore; retrying in %ss",
                        resp.status_code, wait,
                    )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("success"):
                raise OpenDataApiError(f"CKAN datastore_search reported failure: {payload}")
            return payload["result"]

        raise OpenDataApiError(
            f"Exhausted {max_retries} retries contacting CKAN DataStore at {url}"
        )

    def get_fields(self) -> list:
        """Return the resource's field metadata (list of {"id": ..., "type": ...}), no rows."""
        result = self._get({"resource_id": self.resource_id, "limit": 0})
        return result.get("fields", [])

    def fetch_all_records(self, page_size: int = DEFAULT_PAGE_SIZE, fields=None):
        """Yield every record in the resource, paginating with limit/offset.
        If `fields` (list of raw CKAN field ids) is given, only those columns are requested."""
        offset = 0
        total = None
        fetched = 0
        base_params = {"resource_id": self.resource_id, "limit": page_size}
        if fields:
            base_params["fields"] = ",".join(fields)
        while total is None or fetched < total:
            params = dict(base_params, offset=offset)
            result = self._get(params)
            records = result.get("records", [])
            if total is None:
                total = result.get("total", len(records))
            if not records:
                break
            for record in records:
                yield record
            fetched += len(records)
            offset += page_size
