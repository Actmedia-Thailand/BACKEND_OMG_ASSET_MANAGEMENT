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
    "http://localhost:3000",  # Frontend
    "http://127.0.0.1:3000",  # Localhost IP
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
