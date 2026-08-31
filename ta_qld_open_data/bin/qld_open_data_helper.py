import json
import logging
import time

import import_declare_test
from qld_open_data_common import (
    ADDON_NAME,
    DEFAULT_PAGE_SIZE,
    OpenDataStoreClient,
    get_proxy_settings,
    normalize_record_keys,
)
from solnlib import conf_manager, log
from solnlib.modular_input import checkpointer
from splunklib import modularinput as smi


DEFAULT_SOURCETYPE = "qldgov:opendata:record"


def logger_for_input(input_name: str) -> logging.Logger:
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


def _parse_selected_fields(raw_value: str):
    """selected_fields comes from a UCC multipleSelect as a comma-delimited string
    of raw CKAN field ids. Empty/absent means "ingest all fields"."""
    if not raw_value:
        return None
    fields = [f.strip() for f in raw_value.split(",") if f.strip()]
    return fields or None


def validate_input(definition: smi.ValidationDefinition):
    resource_id = definition.parameters.get("resource_id")
    if not resource_id:
        raise ValueError("Resource ID is required.")
    base_url = definition.parameters.get("portal_base_url")
    if not base_url:
        raise ValueError("Open Data Portal base URL is required.")


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    # inputs.inputs is a Python dictionary object like:
    # {
    #   "dataset://<input_name>": {
    #     "portal_base_url": "https://www.data.qld.gov.au",
    #     "resource_id": "<any CKAN DataStore resource_id>",
    #     "selected_fields": "Facility Name,Address",   # optional, comma-delimited raw field ids
    #     "sourcetype": "qldgov:ckan:record",
    #     "page_size": "1000",
    #     "disabled": "0",
    #     "host": "$decideOnStartup",
    #     "index": "<index_name>",
    #     "interval": "<interval_value>",
    #     "python.version": "python3",
    #   },
    # }
    for input_name, input_item in inputs.inputs.items():
        normalized_input_name = input_name.split("/")[-1]
        logger = logger_for_input(normalized_input_name)
        try:
            session_key = inputs.metadata["session_key"]
            log_level = conf_manager.get_log_level(
                logger=logger,
                session_key=session_key,
                app_name=ADDON_NAME,
                conf_name=f"{ADDON_NAME}_settings",
            )
            logger.setLevel(log_level)
            log.modular_input_start(logger, normalized_input_name)

            base_url = input_item.get("portal_base_url", "https://www.data.qld.gov.au")
            resource_id = input_item.get("resource_id")
            sourcetype = input_item.get("sourcetype") or DEFAULT_SOURCETYPE
            selected_fields = _parse_selected_fields(input_item.get("selected_fields"))
            try:
                page_size = int(input_item.get("page_size") or DEFAULT_PAGE_SIZE)
            except (TypeError, ValueError):
                page_size = DEFAULT_PAGE_SIZE
            index = input_item.get("index", "default")

            proxies = get_proxy_settings(session_key, logger)
            client = OpenDataStoreClient(base_url, resource_id, proxies=proxies, logger=logger)

            ckpt = checkpointer.KVStoreCheckpointer(
                f"{ADDON_NAME}_checkpoints", session_key, ADDON_NAME
            )

            ingest_time = time.time()
            count = 0
            for record in client.fetch_all_records(page_size=page_size, fields=selected_fields):
                normalized_record = normalize_record_keys(record)
                event_writer.write_event(
                    smi.Event(
                        data=json.dumps(normalized_record, ensure_ascii=False, default=str),
                        index=index,
                        sourcetype=sourcetype,
                        source=normalized_input_name,
                        time=ingest_time,
                    )
                )
                count += 1

            # Full-snapshot input (CKAN DataStore resources generally have no per-record
            # modified timestamp), so there is no incremental cursor to advance. The
            # checkpoint instead records the last successful run for operators/monitoring.
            ckpt.update(normalized_input_name, {"last_run_epoch": ingest_time, "record_count": count})

            log.events_ingested(
                logger,
                input_name,
                sourcetype,
                count,
                index,
            )
            log.modular_input_end(logger, normalized_input_name)
        except Exception as e:
            log.log_exception(
                logger, e, "qld_open_data_collection_error",
                msg_before=f"Exception raised while ingesting data for input {normalized_input_name}: ",
            )
