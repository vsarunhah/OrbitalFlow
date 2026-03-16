from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routers import alerts, analytics, auth, drafts, email_accounts, jobs, llm_keys, merge_suggestions, recruiters, resumes, tenant_settings

# CORS settings used by middleware and by exception handlers (so error responses get CORS too)
CORS_ORIGINS = ["http://localhost:3000"]
CORS_HEADERS = {
    "Access-Control-Allow-Origin": CORS_ORIGINS[0],
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
}

app = FastAPI(title="JobTracker Backend")


def response_with_cors(response: JSONResponse) -> JSONResponse:
    """Add CORS headers to a response (used by exception handlers so errors are not blocked by CORS)."""
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return response_with_cors(
        JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return response_with_cors(
        JSONResponse(status_code=422, content={"detail": exc.errors()})
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging
    logging.getLogger("uvicorn.error").exception("Unhandled exception")
    detail = "Internal server error"
    if settings.debug:
        detail = f"{detail}: {type(exc).__name__}: {exc}"
    return response_with_cors(
        JSONResponse(status_code=500, content={"detail": detail}),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(llm_keys.router)
app.include_router(email_accounts.router)
app.include_router(jobs.router)
app.include_router(drafts.router)
app.include_router(tenant_settings.router)
app.include_router(alerts.router)
app.include_router(recruiters.router)
app.include_router(merge_suggestions.router)
app.include_router(resumes.router)
app.include_router(analytics.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
