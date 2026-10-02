"""FastAPI routes over the existing analysis, search, RAG, and ingestion services."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Callable

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.analysis import InvalidAnalysisError
from app.api_models import (
    AnalyzeResponse, ComplaintRequest, ErrorResponse, HealthResponse, KBMatchResponse,
    ReadyResponse, ResolveResponse, SearchRequest, SearchResponse, TaxonomyUpdateRequest,
    TaxonomyUpdateResponse, TicketMatchResponse, UpdateResponse,
)
from app.api_service import (
    AdminConfigurationError, ApiServices, UnauthorizedAdminError, build_services,
)
from app.config import get_app_title, get_cors_origins
from app.gemini_client import (
    GeminiProviderError, GeminiRateLimitError, GeminiTimeoutError, MissingApiKeyError,
)
from app.models import KnowledgeBaseArticle, SupportTicket, TaxonomyValue
from app.rag import GroundingError
from app.search import SearchResults
from app.storage import DuplicateRecordError, StorageUnavailableError

logger = logging.getLogger("app.api")


def _error(status: int, code: str, message: str, fields: list[str] | None = None) -> JSONResponse:
    body = ErrorResponse(error={"code": code, "message": message, "fields": fields})
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))


def _matches(results: SearchResults) -> tuple[list[TicketMatchResponse], list[KBMatchResponse]]:
    return (
        [TicketMatchResponse.model_validate(vars(item)) for item in results.tickets],
        [KBMatchResponse.model_validate(vars(item)) for item in results.kb_articles],
    )


def _elapsed(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)


def create_app(service_factory: Callable[[], ApiServices] = build_services) -> FastAPI:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.services = None
        try:
            application.state.services = service_factory()
        except Exception as exc:
            logger.error("service startup failed type=%s", type(exc).__name__)
        try:
            yield
        finally:
            if application.state.services is not None:
                application.state.services.close()

    application = FastAPI(title=get_app_title(), lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Key"],
    )

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error("request failed method=%s", request.method)
            raise
        route = request.scope.get("route")
        route_name = route.path if route is not None else "unmatched"
        logger.info(
            "request method=%s route=%s status=%s latency_ms=%.3f",
            request.method, route_name, response.status_code, _elapsed(start),
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(_request: Request, exc: RequestValidationError):
        fields = [".".join(str(part) for part in error["loc"] if isinstance(part, (str, int)))
                  for error in exc.errors()]
        return _error(422, "validation_error", "Invalid request", fields)

    @application.exception_handler(ValidationError)
    async def pydantic_validation_error(_request: Request, _exc: ValidationError):
        return _error(422, "validation_error", "Invalid request")

    @application.exception_handler(InvalidAnalysisError)
    async def invalid_analysis(_request: Request, _exc: InvalidAnalysisError):
        return _error(502, "invalid_analysis", "Provider returned an invalid analysis")

    @application.exception_handler(GroundingError)
    async def grounding_error(_request: Request, _exc: GroundingError):
        return _error(502, "grounding_error", "Resolution failed citation validation")

    @application.exception_handler(MissingApiKeyError)
    async def missing_key(_request: Request, _exc: MissingApiKeyError):
        return _error(503, "missing_configuration", "Gemini is not configured")

    @application.exception_handler(GeminiRateLimitError)
    async def rate_limit(_request: Request, _exc: GeminiRateLimitError):
        return _error(429, "provider_rate_limit", "Provider rate limit reached")

    @application.exception_handler(GeminiTimeoutError)
    async def timeout(_request: Request, _exc: GeminiTimeoutError):
        return _error(504, "provider_timeout", "Provider request timed out")

    @application.exception_handler(GeminiProviderError)
    async def provider_error(_request: Request, _exc: GeminiProviderError):
        return _error(502, "provider_error", "Provider request failed")

    @application.exception_handler(AdminConfigurationError)
    async def admin_disabled(_request: Request, _exc: AdminConfigurationError):
        return _error(503, "missing_configuration", "Admin API is not configured")

    @application.exception_handler(UnauthorizedAdminError)
    async def unauthorized(_request: Request, _exc: UnauthorizedAdminError):
        return _error(401, "unauthorized", "Admin authorization failed")

    @application.exception_handler(StorageUnavailableError)
    @application.exception_handler(SQLAlchemyError)
    async def storage_error(_request: Request, _exc: Exception):
        return _error(503, "storage_unavailable", "Storage is unavailable")

    @application.exception_handler(DuplicateRecordError)
    async def duplicate_record(_request: Request, _exc: DuplicateRecordError):
        return _error(409, "record_conflict", "Record already exists")

    @application.exception_handler(ValueError)
    async def bad_value(_request: Request, _exc: ValueError):
        return _error(422, "validation_error", "Invalid request or record")

    @application.exception_handler(RuntimeError)
    async def runtime_error(_request: Request, _exc: RuntimeError):
        return _error(503, "search_unavailable", "Search or model is unavailable")

    @application.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", "Request could not be completed")

    @application.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("unexpected API error type=%s", type(exc).__name__)
        return _error(500, "internal_error", "Internal service error")

    def services(request: Request) -> ApiServices:
        result = getattr(request.app.state, "services", None)
        if result is None:
            raise StorageUnavailableError("Services are unavailable")
        return result

    def admin_services(
        service: ApiServices = Depends(services),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ) -> ApiServices:
        service.authorize_admin(x_admin_key)
        return service

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
    def ready(request: Request):
        service = getattr(request.app.state, "services", None)
        details = service.ready() if service is not None else {
            "status": "not_ready", "database": False, "search_index": False,
            "embedding_model": False, "gemini_configured": False,
        }
        response = ReadyResponse.model_validate(details)
        if response.status != "ready":
            return JSONResponse(status_code=503, content=response.model_dump())
        return response

    @application.post("/analyze", response_model=AnalyzeResponse)
    def analyze(body: ComplaintRequest, service: ApiServices = Depends(services)) -> AnalyzeResponse:
        start = perf_counter()
        result = service.analyze(body.complaint)
        return AnalyzeResponse(analysis=result, latency_ms=_elapsed(start))

    @application.post("/search", response_model=SearchResponse)
    def search(body: SearchRequest, service: ApiServices = Depends(services)) -> SearchResponse:
        start = perf_counter()
        results = service.search_complaint(body.complaint, body.top_k_tickets, body.top_k_kb)
        tickets, kb_articles = _matches(results)
        return SearchResponse(tickets=tickets, kb_articles=kb_articles, latency_ms=_elapsed(start))

    @application.post("/resolve", response_model=ResolveResponse)
    def resolve(body: ComplaintRequest, service: ApiServices = Depends(services)) -> ResolveResponse:
        start = perf_counter()
        analysis, results, resolution, non_actionable = service.resolve(body.complaint)
        tickets, kb_articles = _matches(results)
        return ResolveResponse(
            analysis=analysis, tickets=tickets, kb_articles=kb_articles,
            resolution=resolution, source_ids=resolution.sources_used,
            insufficient_evidence=resolution.insufficient_evidence,
            non_actionable=non_actionable,
            latency_ms=_elapsed(start),
        )

    @application.post("/admin/tickets", response_model=UpdateResponse)
    def upsert_ticket(body: SupportTicket, service: ApiServices = Depends(admin_services)) -> UpdateResponse:
        outcome = service.upsert_ticket(body)
        return UpdateResponse(change=outcome.change, index_refreshed=outcome.index_refreshed)

    @application.post("/admin/kb", response_model=UpdateResponse)
    def upsert_kb(body: KnowledgeBaseArticle, service: ApiServices = Depends(admin_services)) -> UpdateResponse:
        outcome = service.upsert_kb_article(body)
        return UpdateResponse(change=outcome.change, index_refreshed=outcome.index_refreshed)

    @application.post("/admin/taxonomy", response_model=TaxonomyUpdateResponse)
    def add_taxonomy(
        body: TaxonomyUpdateRequest, service: ApiServices = Depends(admin_services),
    ) -> TaxonomyUpdateResponse:
        service.add_taxonomy_value(
            TaxonomyValue(kind=body.kind, value=body.value), body.reviewed_by
        )
        return TaxonomyUpdateResponse(status="added")

    return application


app = create_app()
