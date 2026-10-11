import base64
import csv
import gzip
import io
import json

from bikeplan.report import ASSETS


def csv_rows(record, prefix=""):
    for key, value in sorted(record.items()):
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from csv_rows(value, path)
        else:
            yield path, json.dumps(value, sort_keys=True, separators=(",", ":"))


def export_scripts(record, frontier):
    metadata = {
        key: record[key] for key in ("schema_version", "region", "snapshot", "code", "input_hashes")
    }
    curves = {curve["id"]: curve for curve in frontier["scenarios"]}
    packages = {}
    for package in record["packages"]:
        identity = package["identity"]
        pick = {
            **curves[identity["scenario"]]["picks"][identity["rank"]],
            **{key: metric["value"] for key, metric in package["model_totals"].items()},
        }
        payload = {**metadata, "selected": package, "curve_totals": pick}
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(("field", "value_json"))
        writer.writerows(csv_rows(payload))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as archive:
            archive.write(stream.getvalue().encode())
        packages[f"{identity['scenario']}:{identity['rank']}"] = {
            "record": package,
            "csv_gzip": base64.b64encode(compressed.getvalue()).decode("ascii"),
        }
    data = json.dumps(
        {"metadata": metadata, "packages": packages}, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")
    return (
        f'<script type="application/json" id="package-export-data">{data}</script>'
        f"<script>{(ASSETS / 'proposal_exports.js').read_text()}</script>"
    )
