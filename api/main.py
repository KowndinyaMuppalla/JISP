"""JISP FastAPI — MVP entry point"""
import logging, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import reasoning, assets, geoai, timeseries, upload

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("jisp.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("JISP API starting — model: %s", os.getenv("OLLAMA_MODEL","llama3.2"))
    yield
    logger.info("JISP API shutting down")

app = FastAPI(
    title="JISP API",
    description="Jacobs Spatial Intelligence Platform — MVP",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs", redoc_url="/redoc",
)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(reasoning.router, prefix="/api/v1", tags=["Reasoning"])
app.include_router(assets.router,    prefix="/api/v1", tags=["Assets"])
app.include_router(geoai.router,     prefix="/api/v1", tags=["GeoAI"])
app.include_router(timeseries.router,prefix="/api/v1", tags=["Timeseries"])
app.include_router(upload.router,    prefix="/api/v1", tags=["Import"])

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "jisp-api", "version": "1.0.0",
            "model": os.getenv("OLLAMA_MODEL","llama3.2")}
