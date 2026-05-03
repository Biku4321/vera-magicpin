"""
Vera — Magicpin AI Merchant Growth Assistant
Entry point: uvicorn main:app --reload
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv(override=True)   
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# load_dotenv()

from app.api import context, tick, reply, health
from app.store.context_store import ContextStore

store = ContextStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    app.state.store = store
    yield
    await store.disconnect()


app = FastAPI(
    title="Vera",
    description="Magicpin AI Merchant Growth Assistant — Message Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(context.router, prefix="/v1")
app.include_router(tick.router, prefix="/v1")
app.include_router(reply.router, prefix="/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV", "development") == "development",
    )
