"""Read evaluation fixtures without changing the indexed seed corpus."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def held_out_queries() -> list[dict]:
    queries = json.loads((HERE / "held_out_queries.json").read_text(encoding="utf-8"))
    ids = [item["query_id"] for item in queries]
    complaints = [item["complaint"].strip().casefold() for item in queries]
    if len(ids) != len(set(ids)) or len(complaints) != len(set(complaints)):
        raise ValueError("held-out queries must have unique IDs and complaint text")
    return queries


def analysis_cases() -> list[dict]:
    labels = json.loads((HERE / "analysis_labels.json").read_text(encoding="utf-8"))
    held_out = {item["query_id"]: item for item in held_out_queries()}
    cases = []
    for label in labels:
        source = held_out.get(label["query_id"], {})
        cases.append({**source, **label})
    ids = [item["query_id"] for item in cases]
    if len(ids) != len(set(ids)) or any(not item.get("complaint", "").strip() for item in cases):
        raise ValueError("analysis cases must have unique IDs and complaint text")
    return cases
