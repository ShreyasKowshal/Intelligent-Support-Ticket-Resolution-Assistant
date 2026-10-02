"""Admin CLI: ingest one validated JSON record or a reviewed taxonomy value."""

import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pydantic import ValidationError

from app.ingestion import IngestionService
from app.models import KnowledgeBaseArticle, SupportTicket, TaxonomyValue
from app.search import SemanticSearch
from app.seed import seed_database
from app.storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Update reviewed support data")
    commands = parser.add_subparsers(dest="kind", required=True)
    for kind in ("ticket", "kb"):
        command = commands.add_parser(kind)
        command.add_argument("json_file", type=Path, help="JSON object with all validated record fields")
    taxonomy = commands.add_parser("taxonomy")
    taxonomy.add_argument("taxonomy_kind", choices=("product", "category", "severity", "sentiment"))
    taxonomy.add_argument("value")
    taxonomy.add_argument("--reviewed-by", required=True, help="Admin/reviewer name or ID")
    args = parser.parse_args()

    repository = Repository()
    try:
        seed_database(repository)
        search = SemanticSearch(repository)
        service = IngestionService(repository, search)
        if args.kind == "taxonomy":
            service.add_reviewed_taxonomy_value(
                TaxonomyValue(kind=args.taxonomy_kind, value=args.value), args.reviewed_by
            )
            print(f"Added reviewed {args.taxonomy_kind}: {args.value}")
        else:
            payload = json.loads(args.json_file.read_text(encoding="utf-8"))
            if args.kind == "ticket":
                outcome = service.upsert_ticket(SupportTicket.model_validate(payload))
            else:
                outcome = service.upsert_kb_article(KnowledgeBaseArticle.model_validate(payload))
            print(f"{args.kind}: {outcome.change}; index refreshed: {outcome.index_refreshed}")
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        parser.exit(2, f"Update rejected: invalid fields: {fields}\n")
    except (OSError, ValueError):
        parser.exit(2, "Update rejected: check JSON, taxonomy, versions, and timestamps.\n")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
