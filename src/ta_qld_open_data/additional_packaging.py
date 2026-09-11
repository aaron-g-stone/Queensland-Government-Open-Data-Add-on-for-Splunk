"""Post-build hook (see splunk-add-on-ucc-framework docs). ucc-gen fully
regenerates default/restmap.conf, default/web.conf, inputs.conf, and app.conf
on every build, so any hand-edited copies placed under package/default would
either be silently ignored or (worse) clobber the generated CRUD handlers.
Instead we patch the already-generated output here.
"""
import os
import shutil

RESTMAP_MARKER = "admin_external:ta_qld_open_data_open_data_fields"

RESTMAP_SNIPPET = """
[admin_external:ta_qld_open_data_open_data_fields]
handlertype = python
python.version = python3
python.required = 3.9, 3.13
handlerfile = qld_open_data_fields_rh.py
handleractions = list
handlerpersistentmode = true

[admin:ta_qld_open_data_open_data_fields_group]
match = /
members = ta_qld_open_data_open_data_fields
"""


def cleanup_output_files(output_directory, ta_name):
    ta_output = os.path.join(output_directory, ta_name)

    # 1. Merge the custom Open Data field-picker REST endpoint into the UCC-generated restmap.conf.
    restmap_path = os.path.join(ta_output, "default", "restmap.conf")
    if os.path.exists(restmap_path):
        with open(restmap_path, "r") as f:
            content = f.read()
        if RESTMAP_MARKER not in content:
            with open(restmap_path, "a") as f:
                f.write("\n" + RESTMAP_SNIPPET)

    # 2. Mandatory portability fix (see splunk-ta-builder skill Phase 4): remove
    #    compiled charset_normalizer binaries vendored by the build host's pip.
    #    requests automatically falls back to the pure-Python chardet also vendored
    #    here (pinned in lib/requirements.txt), so nothing else needs to change.
    lib_dir = os.path.join(ta_output, "lib")
    if os.path.isdir(lib_dir):
        for entry in os.listdir(lib_dir):
            if entry.startswith("charset_normalizer") or "__mypyc" in entry:
                path = os.path.join(lib_dir, entry)
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.remove(path)
