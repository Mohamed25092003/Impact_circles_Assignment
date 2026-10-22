from contextlib import asynccontextmanager

from fastapi import FastAPI

from Controllers.database import initialize_database
from Helpers.database import engine
from Routes.documents import router as documents_router
from Routes.health import router as health_router
from Routes.content import router as content_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(engine)
    yield


app = FastAPI(title="Impact Circles Financial Documents API", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(health_router)

app.include_router(content_router)
