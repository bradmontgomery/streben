from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import dashboard, activities, strava, fit_upload

app = FastAPI(title="Strava Activity Tracker")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(activities.router)
app.include_router(strava.router)
app.include_router(fit_upload.router)


@app.on_event("startup")
def startup():
    init_db()
