# Queensland Government Open Data Technical Add-on for Splunk

[![Splunk](https://img.shields.io/badge/Splunk-9.x%20%7C%2010.x-black)](https://www.splunk.com)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.13-blue)](https://www.python.org)
[![UCC](https://img.shields.io/badge/built%20with-UCC%20Framework-orange)](https://splunk.github.io/addonfactory-ucc-generator/)

`ta_qld_open_data` collects datasets from the [Queensland Government Open Data Portal](https://www.data.qld.gov.au) — or any other [CKAN](https://ckan.org) portal that exposes the DataStore Action API — and indexes them in Splunk as JSON events.

It ships with one-click presets for eight popular Queensland Government datasets (hospitals, road crash statistics, school locations, and more), but the underlying input is fully generic: point it at any public CKAN `resource_id` and it will collect it.

---

## Features

- **Generic CKAN DataStore collector** — works with any CKAN portal/`resource_id`, not just Queensland's.
- **One-click popular dataset presets** — selecting a preset auto-fills the Resource ID, a sensible field selection, and a matching sourcetype.
- **Live field picker** — a multiselect that queries the portal in real time and lets you choose exactly which columns to ingest, refreshing automatically as you change the Resource ID.
- **Splunk-standard field naming** — source field names (which are often mixed-case with spaces, e.g. `"Hospital and Health Service"`) are automatically normalized to lowercase, underscore-separated Splunk field names (`hospital_and_health_service`) with automatic de-duplication of collisions.
- **No authentication required** — the target API is public and read-only; the add-on ships without an Account/credentials tab.
- **Proxy support** — standard UCC proxy configuration (HTTP/SOCKS4/SOCKS5).
- **Resilient collection** — automatic retry with backoff on timeouts, `429` rate limiting, and `5xx` errors.
- **KV Store checkpointing** — records the last successful run and record count per input for operational visibility.
- **Per-input sourcetype** — override the sourcetype per dataset instead of being locked to one.

## Requirements

| | |
|---|---|
| Splunk platform | Enterprise or Cloud, 9.x or 10.x |
| Python | 3.9+ (Python 3.13-ready) |
| Network access | Outbound HTTPS to the configured Open Data Portal base URL (default `https://www.data.qld.gov.au`) |
| Authentication | None — the target API is public |

## Installation

1. Download the packaged add-on: `ta_qld_open_data-<version>.tar.gz`.
2. In Splunk Web: **Apps → Manage Apps → Install app from file**, and upload the package. Or extract it into `$SPLUNK_HOME/etc/apps/`.
3. Restart Splunk if prompted.
4. The app opens directly to the **Inputs** page.

## Configuration

### Proxy (optional)

**Configuration → Proxy** — standard UCC proxy tab (HTTP/SOCKS4/SOCKS5, optional username/password, optional DNS-via-proxy). Leave disabled if you have direct outbound access.

### Logging

**Configuration → Logging** — set the add-on's log level. Logs land in `index=_internal source=*ta_qld_open_data*`.

## Creating a Data Input

Go to **Inputs → Create New Input → Dataset** and fill in:

| Field | Description |
|---|---|
| **Name** | A unique name for this input. |
| **Interval** | Poll interval in seconds (300–604800). Default `86400` (daily) — most open data reference tables change slowly. Very large datasets (e.g. road crash locations, 400k+ rows) may need a longer interval. |
| **Index** | Destination Splunk index. |
| **Popular dataset** | Optional quick pick. Selecting one auto-fills **Resource ID**, **Fields to ingest**, and **Sourcetype** below. Choose *Custom / other* to configure any dataset manually. |
| **Open Data Portal base URL** | Fixed to `https://www.data.qld.gov.au` (read-only) — this is where all the presets and most public datasets live. |
| **Resource ID** | The CKAN DataStore `resource_id` (UUID) of the dataset to collect. Auto-filled by the preset picker, or find it yourself on the dataset's page/API info panel. |
| **Fields to ingest** | Multiselect, live-populated from the portal once Resource ID is set. Leave empty to ingest every field. Labels show the resulting Splunk field name; auto-filled with the full field list when you pick a preset. |
| **Sourcetype** | Assigned to ingested events. Auto-filled as `qldgov:opendata:<dataset>` for presets; edit freely for custom resources. |
| **Page size** | Records per API page (advanced). Default `1000`. |

### Popular dataset presets

| Dataset | Sourcetype | Approx. records |
|---|---|---|
| Queensland Public Hospitals | `qldgov:opendata:hospitals` | 201 |
| Hospital Performance — Facilities | `qldgov:opendata:hospital_performance` | 32 |
| Active Mobile Speed Camera Sites | `qldgov:opendata:speed_cameras` | 3,686 |
| Road Crash Locations (QLD Roads) | `qldgov:opendata:road_crash_locations` | 415,000+ |
| Road Crash Casualties (QLD Roads) | `qldgov:opendata:road_crash_casualties` | 38,893 |
| State & Non-State School Details | `qldgov:opendata:schools` | 1,774 |
| Transport Customer Service Centres | `qldgov:opendata:transport_centres` | 263 |
| Cadastral Key Maps — Queensland | `qldgov:opendata:cadastral_maps` | 16 |

Custom/other resources default to `qldgov:opendata:record`.

> **Tip:** Road Crash Locations is large. At the default daily interval this is a meaningful daily indexing volume — consider a longer interval or trimming fields via the field picker.

## How it works

- **Full-snapshot polling.** CKAN DataStore resources generally have no per-record "last modified" timestamp, so each poll re-ingests the resource's current full snapshot as events (one event per record). A KV Store checkpoint records the last successful run time and record count per input for monitoring, but there's no incremental cursor to advance.
- **Field naming.** Every ingested record's keys are normalized: lowercased, non-alphanumeric runs collapsed to a single underscore, no leading/trailing underscores, digit-leading names get an `f_` prefix, and CKAN's synthetic row identifier `_id` is renamed to `ckan_id` (so it isn't hidden by Splunk's convention of hiding underscore-prefixed fields). Collisions within a record get a numeric suffix so no data is silently dropped.
- **Live field picker.** A custom read-only REST endpoint (`qld_open_data_fields_rh.py`) calls the portal's `datastore_search` with `limit=0` to fetch field metadata without rows, whenever the Open Data Portal base URL or Resource ID change.
- **Selective field requests.** If you select specific fields, the collector passes CKAN's `fields` parameter so only those columns are requested from the API, reducing payload size.

## Project structure

```
ta_qld_open_data/
├── globalConfig.json          # UCC config: pages, inputs, field definitions, presets
├── additional_packaging.py    # Post-build hook (see below)
└── package/
    ├── app.manifest
    ├── bin/
    │   ├── qld_open_data_common.py       # Shared CKAN DataStore client, proxy/conf helpers, field normalization
    │   ├── qld_open_data_helper.py       # Modular input: polls the API, writes events, checkpoints
    │   └── qld_open_data_fields_rh.py    # Custom admin_external REST handler backing the live field picker
    ├── default/
    │   └── props.conf          # Sourcetype definitions (JSON KV_MODE) for each preset + generic default
    ├── lib/
    │   └── requirements.txt    # Pinned, pure-Python dependencies (see Portability below)
    └── static/                 # App icons
```

## Building from source

Requires [`splunk-add-on-ucc-framework`](https://splunk.github.io/addonfactory-ucc-generator/) and `splunk-appinspect`.

```bash
pip install splunk-add-on-ucc-framework splunk-appinspect

# Build
ucc-gen build --source package --ta-version <version>

# Package
ucc-gen package --path output/ta_qld_open_data

# Validate
splunk-appinspect inspect ta_qld_open_data-<version>.tar.gz --mode precert --included-tags cloud
```

### `additional_packaging.py`

`ucc-gen build` fully regenerates `restmap.conf` on every build, so the live field picker's custom REST endpoint can't be shipped as a static conf file in `package/default/` — it would either be ignored or clobber the CRUD handlers UCC generates for inputs/settings. Instead, `additional_packaging.py` runs after every build and:

1. Appends the field picker's `admin_external` stanza to the generated `restmap.conf`.
2. Removes compiled `charset_normalizer` binaries from `lib/` (see Portability below) automatically, so that step doesn't need to be run by hand.

### Portability

The `lib/requirements.txt` dependencies are pinned to pure-Python wheels (`requests[socks]==2.32.3`, `chardet==5.2.0`, `solnlib>=7.0.0,<8`) so the package runs on Python 3.9+ regardless of build host architecture. `solnlib` is capped below `8` because `solnlib>=8` pulls in gRPC/OpenTelemetry dependencies that require Python 3.10+. Run the portability check after any dependency change:

```bash
python verify_portability.py output/ta_qld_open_data --target-python 3.9
```

## License

See [`LICENSES/LICENSE.txt`](package/LICENSES/LICENSE.txt).

## Support

This is a community-built add-on, not an official Splunk or Queensland Government product. Open an issue in this repository for bugs or feature requests.