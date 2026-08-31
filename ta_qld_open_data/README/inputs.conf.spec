[dataset://<name>]
index = (Default: default)
interval = Polling interval in seconds. Most open data reference datasets change slowly; daily (86400) is a reasonable default. Very large datasets (e.g. road crash locations, 400k+ rows) may need a longer interval. (Default: 86400)
known_dataset = Pick a well-known Queensland Government open dataset to auto-fill its Resource ID below, or choose Custom to enter any CKAN DataStore resource_id yourself (from data.qld.gov.au or another CKAN portal). (Default: custom)
page_size = Number of records to request per datastore_search page (advanced; default 1000 works for most datasets). (Default: 1000)
portal_base_url = Base URL of the Queensland Government Open Data Portal (fixed; all presets and most public datasets live here). (Default: https://www.data.qld.gov.au)
resource_id = The dataset's resource_id on the Open Data Portal. Auto-filled if you picked a popular dataset above, or find it yourself on the dataset's page/API info panel (look for resource_id in the URL or the API example snippet).
selected_fields = Choose which fields to ingest. The list refreshes automatically from the Open Data Portal once the base URL and Resource ID are filled in. Leave empty to ingest every field. Labels show the resulting Splunk field name (Splunk naming standard: lowercase, underscores only); values sent to the API are the original source field ids.
sourcetype = Sourcetype assigned to ingested events. Auto-filled as qldgov:opendata:<dataset> when you pick a popular dataset above; edit freely for custom resources. (Default: qldgov:opendata:record)
python.required = {3.7|3.9|3.13}
* For Python scripts only, selects which Python version to use.
* Set to "3.9" to use the Python 3.9 version.
* Set to "3.13" to use the Python 3.13 version.
* Optional.
* Default: not set
