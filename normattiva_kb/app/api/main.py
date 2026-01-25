from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Normattiva KB")
app.include_router(router)
