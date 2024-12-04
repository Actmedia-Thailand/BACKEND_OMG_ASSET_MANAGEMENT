from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.user import router as user_router
from app.asset import router as asset_router
from app.view import router as view_router
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

# Create a Limiter object. 30 request per minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

# Create the FastAPI app
app = FastAPI()

# Add CORS Middleware
origins = [
    "http://localhost:3000",  # Frontend
    "http://127.0.0.1:3000",  # Localhost IP
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST, GET, DELETE, PUT"],#only Browser Post man still send every method such as patch
    allow_headers=["Content-Type", "Authorization"],
)

# Add the SlowAPI Middleware
app.state.limiter = limiter  # Set the limiter to the app's state
app.add_middleware(SlowAPIMiddleware)  # No arguments are passed here

# Include routers
app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(view_router, prefix="/view", tags=["View"])
app.include_router(asset_router, prefix="/asset", tags=["Asset"])
