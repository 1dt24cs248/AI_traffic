"""CORS settings for the browser frontends used during local development."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


FRONTEND_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # Keep compatibility with the project's documented legacy local UI port.
    "http://localhost:3000",
)


def configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(FRONTEND_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
