from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routes.conversation_routes import router as conversation_router
from backend.routes.agent_routes import router as agent_router
from backend.routes.ticket_routes import router as ticket_router
from backend.routes.knowledge_base_routes import router as knowledge_base_router
from backend.utils.knowledge_base import seed_knowledge_base

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.include_router(ticket_router)
app.include_router(agent_router)
app.include_router(conversation_router)
app.include_router(knowledge_base_router)


@app.on_event("startup")
async def startup_event():
    seed_knowledge_base()


@app.get("/health")
def health_check():
    return {"status": "ok"}