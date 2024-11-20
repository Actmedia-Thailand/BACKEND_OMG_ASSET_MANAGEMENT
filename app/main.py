from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.user import router as user_router

app = FastAPI()

# เพิ่ม CORS Middleware แบบเสรี
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # อนุญาตทุก origin
    allow_credentials=True,
    allow_methods=["*"],  # อนุญาตทุก HTTP method (GET, POST, PUT, DELETE, ฯลฯ)
    allow_headers=["*"],  # อนุญาตทุก header
)

# Include User Router
app.include_router(user_router, prefix="/users", tags=["Users"])
