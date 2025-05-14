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
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from app.user import router as user_router
from app.asset import router as asset_router
from app.asset2 import router as asset2_router
from app.asset3 import router as asset3_router
from app.view import router as view_router
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime
from app.sheets_service import get_google_sheets_service

# กำหนดการตั้งค่า log
logging.basicConfig(
    filename='api_logs.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        client_ip = request.client.host
        method = request.method
        path = request.url.path
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"IP: {client_ip} - เมธอด: {method} - เส้นทาง: {path} - เวลา: {timestamp}")
        response = await call_next(request)
        logger.info(f"IP: {client_ip} - เมธอด: {method} - เส้นทาง: {path} - สถานะ: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Error: {str(e)} - IP: {client_ip} - Path: {path}")
        raise

# Include routers
# Include the asset3_router with a prefix and tags
# - prefix="/asset3": adds this prefix to all routes in the router (e.g., "/list" becomes "/asset3/list")
# - tags=["Asset3"]: used only for organizing routes in the Swagger UI (/docs), not required for functionality
app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(view_router, prefix="/view", tags=["View"])
app.include_router(asset_router, prefix="/asset", tags=["Asset"])
app.include_router(asset2_router, prefix="/asset2", tags=["Asset2"])
app.include_router(asset3_router, prefix="/asset3", tags=["Asset3"])
