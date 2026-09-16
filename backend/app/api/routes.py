from fastapi import APIRouter, HTTPException

from ..schemas import (
    ClassificationRequest,
    ComplianceFacts,
    CorpusResponse,
    LanguageCatalogEntry,
    LanguagesResponse,
    QueryRequest,
    QueryResponse,
)
from ..services.ai_service import ai_service
from ai.person_b_retrieval.schema import Classification
from ai.shared.languages import LANGUAGE_CATALOG
from ai.translation import translator_configured

router = APIRouter(tags=["AI"])


@router.get("/languages", response_model=LanguagesResponse)
def languages() -> LanguagesResponse:
    """Safe language-capability catalog for the picker (spec section 24).

    Never touches or exposes BHASHINI_API_KEY/BHASHINI_USER_ID — only
    whether a real backend is configured at all. Returns the local
    static catalog rather than querying Bhashini's own capability API,
    since that would require a live call on every page load and this
    catalog does not change at runtime.
    """
    return LanguagesResponse(
        configured=translator_configured(ai_service.translator),
        languages=[
            LanguageCatalogEntry(code=e.code, name=e.name, native_name=e.native_name)
            for e in LANGUAGE_CATALOG
        ],
    )


@router.get("/corpus", response_model=CorpusResponse)
def corpus_status() -> CorpusResponse:
    try:
        return CorpusResponse(
            collection=ai_service.store.collection.name,
            chunks=ai_service.corpus_count(),
            jurisdictions=ai_service.corpus_jurisdictions(),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Corpus unavailable: {exc}") from exc


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    classification = None
    if request.classification:
        c = request.classification
        if any(v is not None for v in (c.formulation_type, c.source_organism, c.jurisdiction)):
            classification = Classification(
                formulation_type=c.formulation_type,
                source_organism=c.source_organism,
                jurisdiction=c.jurisdiction,
            )

    # exclude_none matters: the compliance layer distinguishes "unknown"
    # (ask the user) from False. Serialising unset optionals as None and
    # passing them through would let the context layer see an explicit None
    # where it should see an absent key, which is the same value here but
    # would stop being so the moment a default changes.
    facts = (
        request.compliance_facts.model_dump(exclude_none=True)
        if request.compliance_facts
        else None
    )

    try:
        result = ai_service.answer(
            request.query,
            classification,
            request.top_k,
            compliance_facts=facts,
            consented_acts=set(request.consent_licensed_acts),
            language=request.language,
            scope=request.scope,
        )
        return QueryResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc
