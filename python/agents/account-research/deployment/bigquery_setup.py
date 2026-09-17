"""Load the CRM master ledger into a BigQuery table.

Mirrors the fomc-research sample's bigquery_setup.py, but the source is this
repo's data/master/contacts.json rather than a CSV. The resulting
<dataset>.contacts table is what the gcp-bigquery MCP server and the agent's
warehouse step query.

    python bigquery_setup.py --project_id=$GOOGLE_CLOUD_PROJECT \
        --dataset_id=$GOOGLE_CLOUD_BQ_DATASET --location=$GOOGLE_CLOUD_LOCATION

Re-running replaces the table (WRITE_TRUNCATE), so it is safe after each
weekly sync.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from absl import app, flags
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

FLAGS = flags.FLAGS
flags.DEFINE_string("project_id", None, "GCP project ID.")
flags.DEFINE_string("dataset_id", None, "BigQuery dataset ID.")
flags.DEFINE_string("table_id", "contacts", "BigQuery table ID.")
flags.DEFINE_string("location", "us-central1", "Location for the dataset.")
flags.DEFINE_string(
    "ledger",
    str(Path(__file__).resolve().parents[4] / "data" / "master" / "contacts.json"),
    "Path to the master ledger JSON.",
)
flags.mark_flags_as_required(["project_id", "dataset_id"])

SCHEMA = [
    bigquery.SchemaField("contact_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("first_name", "STRING"),
    bigquery.SchemaField("last_name", "STRING"),
    bigquery.SchemaField("email", "STRING"),
    bigquery.SchemaField("phone", "STRING"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("seniority", "STRING"),
    bigquery.SchemaField("linkedin_url", "STRING"),
    bigquery.SchemaField("location", "STRING"),
    bigquery.SchemaField("company_name", "STRING"),
    bigquery.SchemaField("company_domain", "STRING"),
    bigquery.SchemaField("industry", "STRING"),
    bigquery.SchemaField("employee_count", "INT64"),
    bigquery.SchemaField("technologies", "STRING", mode="REPEATED"),
    bigquery.SchemaField("apollo_contact_id", "STRING"),
    bigquery.SchemaField("apollo_person_id", "STRING"),
    bigquery.SchemaField("explorium_prospect_id", "STRING"),
    bigquery.SchemaField("explorium_business_id", "STRING"),
    bigquery.SchemaField("sources", "STRING", mode="REPEATED"),
    # Provenance is a per-field map; kept as a JSON string so the table stays
    # flat and the schema never has to change when a field is added.
    bigquery.SchemaField("provenance_json", "STRING"),
    bigquery.SchemaField("first_seen", "TIMESTAMP"),
    bigquery.SchemaField("last_updated", "TIMESTAMP"),
]


def create_dataset(client: bigquery.Client, dataset_id: str, location: str) -> bigquery.Dataset:
    dataset = bigquery.Dataset(bigquery.DatasetReference(client.project, dataset_id))
    dataset.location = location
    dataset.description = "CRM master ledger mirror, loaded from data/master/contacts.json"
    dataset = client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset {client.project}.{dataset_id} ready ({location})")
    return dataset


def rows_from_ledger(path: Path) -> list[dict]:
    raw = json.loads(path.read_text() or "{}")
    rows = []
    for c in raw.get("contacts", []):
        row = {k: c.get(k) for k in (
            "contact_id", "first_name", "last_name", "email", "phone", "title",
            "seniority", "linkedin_url", "location", "company_name",
            "company_domain", "industry", "employee_count", "technologies",
            "apollo_contact_id", "apollo_person_id", "explorium_prospect_id",
            "explorium_business_id", "sources", "first_seen", "last_updated",
        )}
        row["technologies"] = row.get("technologies") or []
        row["sources"] = row.get("sources") or []
        row["provenance_json"] = json.dumps(c.get("provenance") or {}, sort_keys=True)
        # Empty strings are not timestamps.
        for ts in ("first_seen", "last_updated"):
            if not row.get(ts):
                row[ts] = None
        rows.append(row)
    return rows


def load_table(client: bigquery.Client, dataset_id: str, table_id: str, rows: list[dict]) -> None:
    table_ref = f"{client.project}.{dataset_id}.{table_id}"
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()
    table = client.get_table(table_ref)
    print(f"Loaded {table.num_rows} rows into {table_ref}")


def main(argv: Sequence[str]) -> None:
    del argv
    ledger = Path(FLAGS.ledger)
    if not ledger.exists():
        raise SystemExit(f"Ledger not found: {ledger}")
    rows = rows_from_ledger(ledger)
    if not rows:
        raise SystemExit(f"Ledger {ledger} holds no contacts; nothing to load")

    client = bigquery.Client(project=FLAGS.project_id)
    try:
        create_dataset(client, FLAGS.dataset_id, FLAGS.location)
        load_table(client, FLAGS.dataset_id, FLAGS.table_id, rows)
    except GoogleCloudError as exc:
        raise SystemExit(f"BigQuery error: {exc}") from exc


if __name__ == "__main__":
    app.run(main)
