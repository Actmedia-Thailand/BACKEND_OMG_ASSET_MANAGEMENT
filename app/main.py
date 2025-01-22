"""
    FastAPI Main Application Module
    ==============================

    This module initializes and configures the main FastAPI application with CORS,
    rate limiting, and route registration.

    **Features**

        * CORS (Cross-Origin Resource Sharing) middleware configuration
        * Rate limiting using SlowAPI
        * API route registration for different modules (users, assets, views)

    **Implementation Details**

        * Rate limiting: 100 requests per minute per IP address
        * CORS: Configured for local development (localhost:3000)
        * Modular routing: Separate routers for users, assets, and views

    **Dependencies**

        * FastAPI: Web framework for building APIs
        * SlowAPI: Rate limiting middleware
        * CORS Middleware: Handle Cross-Origin Resource Sharing

    **Routers**

        * /users: User management endpoints
        * /view: View management endpoints
        * /asset: Asset management endpoints
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.user import router as user_router
from app.asset import router as asset_router
from app.view import router as view_router
from slowapi import Limiter
from slowapi.util import get_remote_address


# Create a Limiter object. 30 request per minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Create the FastAPI app
app = FastAPI()

# Add CORS Middleware
origins = [
    "*",  # อนุญาตทุก IP
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # ระบุ origins ที่อนุญาต
    allow_credentials=True,  # อนุญาตส่ง credentials (cookies, headers)
    allow_methods=["*"],  # อนุญาตทุก HTTP method
    allow_headers=["*"],  # อนุญาตทุก header
)

# Add the SlowAPI Middleware
app.state.limiter = limiter  # Set the limiter to the app's state


# Include routers
app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(view_router, prefix="/view", tags=["View"])
app.include_router(asset_router, prefix="/asset", tags=["Asset"])
