"""Small SQLAlchemy Core repository; SQLite is the local default."""

import os
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.exc import ArgumentError, IntegrityError, SQLAlchemyError

from app.models import EmbeddingMetadata, KnowledgeBaseArticle, SupportTicket, TaxonomyValue

metadata = MetaData()

tickets = Table(
    "tickets",
    metadata,
    Column("ticket_id", String(32), primary_key=True),
    Column("complaint", Text, nullable=False),
    Column("product", String(80), nullable=False),
    Column("category", String(80), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("sentiment", String(16), nullable=False),
    Column("resolution", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("approved", Boolean, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

kb_articles = Table(
    "kb_articles",
    metadata,
    Column("kb_id", String(32), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("content", Text, nullable=False),
    Column("category", String(80), nullable=False),
    Column("approved", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

taxonomy_values = Table(
    "taxonomy_values",
    metadata,
    Column("kind", String(16), primary_key=True),
    Column("value", String(80), primary_key=True),
)

embeddings = Table(
    "embeddings",
    metadata,
    Column("source_id", String(32), primary_key=True),
    Column("source_type", String(8), primary_key=True),
    Column("model_name", String(120), primary_key=True),
    Column("model_version", String(80), primary_key=True),
    Column("vector_bytes", LargeBinary, nullable=True),
    Column("updated_at", String(40), nullable=False),
)


class DuplicateRecordError(ValueError):
    """A record with the same stable ID already exists."""


class UnknownTaxonomyValueError(ValueError):
    """A record uses an unregistered product or category."""


class StorageUnavailableError(RuntimeError):
    """The configured database cannot be used."""


class Repository:
    def __init__(self, database_url: str | URL | None = None) -> None:
        if database_url is None:
            database_url = os.getenv("DATABASE_URL") or None
        if database_url is None:
            db_path = Path(__file__).resolve().parents[1] / "data" / "support.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            database_url = URL.create("sqlite", database=str(db_path))
        try:
            url = make_url(database_url)
            # Render supplies postgresql://; old providers may supply postgres://.
            # Use the installed psycopg driver without altering local SQLite URLs.
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            self.engine: Engine = create_engine(url)
        except (ArgumentError, ImportError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Invalid or unsupported DATABASE_URL. Leave it unset for local SQLite."
            ) from exc

    def initialize(self) -> None:
        try:
            metadata.create_all(self.engine)
        except SQLAlchemyError as exc:
            raise StorageUnavailableError(
                "Database unavailable. Check DATABASE_URL, or leave it unset for local SQLite."
            ) from exc

    def close(self) -> None:
        self.engine.dispose()

    def add_taxonomy_value(self, item: TaxonomyValue) -> None:
        with self.engine.begin() as connection:
            try:
                connection.execute(insert(taxonomy_values).values(**item.model_dump()))
            except IntegrityError as exc:
                raise DuplicateRecordError(f"taxonomy value already exists: {item.kind}/{item.value}") from exc

    def list_taxonomy(self, kind: str) -> list[str]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(taxonomy_values.c.value)
                .where(taxonomy_values.c.kind == kind)
                .order_by(taxonomy_values.c.value)
            )
            return list(rows.scalars())

    def add_ticket(self, ticket: SupportTicket) -> None:
        with self.engine.begin() as connection:
            self._validate_ticket_taxonomy(connection, ticket)
            try:
                connection.execute(insert(tickets).values(**ticket.model_dump(mode="json")))
            except IntegrityError as exc:
                raise DuplicateRecordError(f"ticket already exists: {ticket.ticket_id}") from exc

    def upsert_ticket(self, ticket: SupportTicket) -> str:
        """Insert or replace a stable ID in one portable transaction."""
        ticket = SupportTicket.model_validate(ticket.model_dump())
        with self.engine.begin() as connection:
            self._validate_ticket_taxonomy(connection, ticket)
            row = connection.execute(
                select(tickets).where(tickets.c.ticket_id == ticket.ticket_id)
            ).mappings().first()
            if row is None:
                connection.execute(insert(tickets).values(**ticket.model_dump(mode="json")))
                return "inserted"
            previous = SupportTicket.model_validate(row)
            if ticket.created_at != previous.created_at:
                raise ValueError("created_at cannot change for an existing ticket")
            if ticket == previous:
                return "unchanged"
            if ticket.updated_at <= previous.updated_at:
                raise ValueError("updated_at must advance when a ticket changes")
            connection.execute(
                update(tickets).where(tickets.c.ticket_id == ticket.ticket_id)
                .values(**ticket.model_dump(mode="json"))
            )
            return "updated"

    def add_kb_article(self, article: KnowledgeBaseArticle) -> None:
        with self.engine.begin() as connection:
            self._validate_category(connection, article.category)
            try:
                connection.execute(insert(kb_articles).values(**article.model_dump(mode="json")))
            except IntegrityError as exc:
                raise DuplicateRecordError(f"KB article already exists: {article.kb_id}") from exc

    def upsert_kb_article(self, article: KnowledgeBaseArticle) -> str:
        """Preserve a KB ID and require a new version when guidance changes."""
        article = KnowledgeBaseArticle.model_validate(article.model_dump())
        with self.engine.begin() as connection:
            self._validate_category(connection, article.category)
            row = connection.execute(
                select(kb_articles).where(kb_articles.c.kb_id == article.kb_id)
            ).mappings().first()
            if row is None:
                connection.execute(insert(kb_articles).values(**article.model_dump(mode="json")))
                return "inserted"
            previous = KnowledgeBaseArticle.model_validate(row)
            if article.created_at != previous.created_at:
                raise ValueError("created_at cannot change for an existing KB article")
            if article == previous:
                return "unchanged"
            if article.updated_at <= previous.updated_at:
                raise ValueError("updated_at must advance when a KB article changes")
            text_changed = (
                article.title, article.content, article.category
            ) != (previous.title, previous.content, previous.category)
            if article.version < previous.version or (text_changed and article.version <= previous.version):
                raise ValueError("KB version must advance when content changes and never decrease")
            connection.execute(
                update(kb_articles).where(kb_articles.c.kb_id == article.kb_id)
                .values(**article.model_dump(mode="json"))
            )
            return "updated"

    def get_ticket(self, ticket_id: str, evidence_only: bool = False) -> SupportTicket | None:
        statement = select(tickets).where(tickets.c.ticket_id == ticket_id)
        if evidence_only:
            statement = statement.where(tickets.c.status == "resolved", tickets.c.approved.is_(True))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
            return SupportTicket.model_validate(row) if row else None

    def get_kb_article(self, kb_id: str, evidence_only: bool = False) -> KnowledgeBaseArticle | None:
        statement = select(kb_articles).where(kb_articles.c.kb_id == kb_id)
        if evidence_only:
            statement = statement.where(kb_articles.c.approved.is_(True))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
            return KnowledgeBaseArticle.model_validate(row) if row else None

    def list_tickets(self, evidence_only: bool = False) -> list[SupportTicket]:
        statement = select(tickets).order_by(tickets.c.ticket_id)
        if evidence_only:
            statement = statement.where(tickets.c.status == "resolved", tickets.c.approved.is_(True))
        with self.engine.connect() as connection:
            return [SupportTicket.model_validate(row) for row in connection.execute(statement).mappings()]

    def list_kb_articles(self, evidence_only: bool = False) -> list[KnowledgeBaseArticle]:
        statement = select(kb_articles).order_by(kb_articles.c.kb_id)
        if evidence_only:
            statement = statement.where(kb_articles.c.approved.is_(True))
        with self.engine.connect() as connection:
            return [KnowledgeBaseArticle.model_validate(row) for row in connection.execute(statement).mappings()]

    def get_embedding(
        self, source_id: str, source_type: str, model_name: str, model_version: str
    ) -> EmbeddingMetadata | None:
        key = (
            embeddings.c.source_id == source_id,
            embeddings.c.source_type == source_type,
            embeddings.c.model_name == model_name,
            embeddings.c.model_version == model_version,
        )
        with self.engine.connect() as connection:
            row = connection.execute(select(embeddings).where(*key)).mappings().first()
            return EmbeddingMetadata.model_validate(row) if row else None

    def save_embedding(self, item: EmbeddingMetadata) -> None:
        """Store an encoded vector without exposing SQL to the search layer."""
        if not item.vector_bytes:
            raise ValueError("embedding vector_bytes cannot be empty")
        key = (
            embeddings.c.source_id == item.source_id,
            embeddings.c.source_type == item.source_type,
            embeddings.c.model_name == item.model_name,
            embeddings.c.model_version == item.model_version,
        )
        values = item.model_dump()
        values["updated_at"] = item.updated_at.isoformat()
        with self.engine.begin() as connection:
            # Only the current text version is useful for this source/model.
            connection.execute(delete(embeddings).where(
                embeddings.c.source_id == item.source_id,
                embeddings.c.source_type == item.source_type,
                embeddings.c.model_name == item.model_name,
                embeddings.c.model_version != item.model_version,
            ))
            exists = connection.execute(select(embeddings.c.source_id).where(*key)).first()
            if exists:
                connection.execute(update(embeddings).where(*key).values(**values))
            else:
                connection.execute(insert(embeddings).values(**values))

    def seed(
        self,
        taxonomy: list[TaxonomyValue],
        ticket_records: list[SupportTicket],
        articles: list[KnowledgeBaseArticle],
    ) -> dict[str, int]:
        """Insert missing seed IDs in one transaction; leave existing records intact."""
        counts = {"taxonomy": 0, "tickets": 0, "kb_articles": 0}
        with self.engine.begin() as connection:
            for item in taxonomy:
                key = (item.kind, item.value)
                exists = connection.execute(
                    select(taxonomy_values.c.value).where(
                        taxonomy_values.c.kind == key[0], taxonomy_values.c.value == key[1]
                    )
                ).first()
                if not exists:
                    connection.execute(insert(taxonomy_values).values(**item.model_dump()))
                    counts["taxonomy"] += 1
            for ticket in ticket_records:
                self._validate_ticket_taxonomy(connection, ticket)
                exists = connection.execute(
                    select(tickets.c.ticket_id).where(tickets.c.ticket_id == ticket.ticket_id)
                ).first()
                if not exists:
                    connection.execute(insert(tickets).values(**ticket.model_dump(mode="json")))
                    counts["tickets"] += 1
            for article in articles:
                self._validate_category(connection, article.category)
                exists = connection.execute(
                    select(kb_articles.c.kb_id).where(kb_articles.c.kb_id == article.kb_id)
                ).first()
                if not exists:
                    connection.execute(insert(kb_articles).values(**article.model_dump(mode="json")))
                    counts["kb_articles"] += 1
        return counts

    @staticmethod
    def _known(connection: Connection, kind: str, value: str) -> bool:
        return connection.execute(
            select(taxonomy_values.c.value).where(
                taxonomy_values.c.kind == kind, taxonomy_values.c.value == value
            )
        ).first() is not None

    def _validate_category(self, connection: Connection, category: str) -> None:
        if not self._known(connection, "category", category):
            raise UnknownTaxonomyValueError(f"unknown category: {category}")

    def _validate_ticket_taxonomy(self, connection: Connection, ticket: SupportTicket) -> None:
        if not self._known(connection, "product", ticket.product):
            raise UnknownTaxonomyValueError(f"unknown product: {ticket.product}")
        self._validate_category(connection, ticket.category)
        if not self._known(connection, "severity", ticket.severity):
            raise UnknownTaxonomyValueError(f"unknown severity: {ticket.severity}")
        if not self._known(connection, "sentiment", ticket.sentiment):
            raise UnknownTaxonomyValueError(f"unknown sentiment: {ticket.sentiment}")
