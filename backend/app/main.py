from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_investigations import router as investigations_router
from app.api.routes_repositories import router as repositories_router
from app.api.routes_graph import router as graph_router
from app.api.routes_overview import router as overview_router
from app.api.routes_chat import router as chat_router
from app.config import settings
from app.exceptions import register_exception_handlers
from app.logging_config import setup_logging
from app.middleware import RequestContextMiddleware

setup_logging(settings.LOG_LEVEL)

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# CORS middleware to allow frontend (localhost:3000) to communicate with backend (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(health_router)


@app.get("/health", include_in_schema=False)
def root_health() -> dict[str, str]:
    # Alias for frontend checkHealth(): the versioned route lives at
    # /api/v1/health; this bare path keeps liveness probing working.
    return {"status": "ok", "service": settings.APP_NAME}


app.include_router(repositories_router)
app.include_router(graph_router)
app.include_router(overview_router)
app.include_router(investigations_router)
app.include_router(chat_router)
