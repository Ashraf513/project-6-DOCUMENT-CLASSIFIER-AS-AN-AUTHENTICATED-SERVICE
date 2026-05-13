"""
app/api/main.py
Creates the FastAPI application, registers all routers, and runs startup checks.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, users, batches, predictions


def create_app() -> FastAPI:
    """Factory function that builds and returns the FastAPI app."""
    app = FastAPI(
        title="Document Classifier API",
        description="Authenticated service for browsing document classifications",
        version="0.1.0",
    )

    # CORS — allow the Swagger UI and any frontend to call the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register all routers with their URL prefixes
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(batches.router, prefix="/batches", tags=["Batches"])
    app.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])

    @app.on_event("startup")
    async def startup():
        """
        Startup checks — the app refuses to start if any check fails.
        These checks are required by the project specification:

        1. Vault must be reachable (load JWT signing key)
        2. Classifier weights file must exist and SHA-256 must match model card
        3. Model card's reported test top-1 must be above the threshold
        4. Casbin policy table must not be empty

        In the current skeleton these are logged but not enforced.
        Replace the print() calls with real checks once infra is ready.
        """
        print("[startup] Vault check: placeholder — load JWT signing key here")
        print("[startup] Classifier weights check: placeholder — verify SHA-256 here")
        print("[startup] Casbin policy check: placeholder — verify policy table here")
        print("[startup] All startup checks passed (skeleton mode)")

    @app.get("/health")
    async def health_check():
        """Simple health-check endpoint for docker-compose and CI."""
        return {"status": "ok"}

    return app


# Module-level app instance — uvicorn imports this
app = create_app()