from fastapi import FastAPI
from user import router as user_router

app = FastAPI()

# Include User Router
app.include_router(user_router, prefix="/users", tags=["Users"])
