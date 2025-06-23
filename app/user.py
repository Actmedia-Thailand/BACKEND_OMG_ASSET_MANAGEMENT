"""
    User Management Module
    =====================

    This module provides a FastAPI router for managing users in a Google Sheets document.
    It implements user authentication, registration, and CRUD operations.

    **Features**

        * Google Sheets integration for user data storage
        * JWT-based authentication
        * Password hashing with bcrypt
        * Google OAuth2 integration
        * User session management

    **API Endpoints**

        * GET /: Retrieve all users
        * GET /{user_id}: Get user by ID
        * POST /register: Register new user
        * POST /login: User login
        * POST /reset_password: Reset user password
        * PUT /{user_id}: Update user
        * DELETE /{user_id}: Delete user
        * GET /google_signup: Google OAuth2 signup/login
        * GET /protected: Protected route example

    **Configuration**

        * Uses Google Sheets API v4
        * JWT token configuration
        * OAuth2 credentials
        * Password hashing settings

    **Dependencies**

        * FastAPI: Web framework
        * google-auth: Google authentication
        * bcrypt: Password hashing
        * PyJWT: JWT token handling
        * requests: HTTP client for OAuth2
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Response, Request as FastAPIRequest  
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4
import requests
import bcrypt
import jwt
from app.sheets_service import get_google_sheets_service
import os
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env into environment

# === Configuration ===
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
USER_SHEET_RANGE = 'User'

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days in minutes

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()

# === Helper Functions ===

## Google Sheets Helper

def convert_value(value: str):
    """
        Convert string values to appropriate Python types.

        **Input:**

            - value (str): String value to convert
            
        **Process:**

            1. Try converting to integer
            2. Try converting to float
            3. Try converting to boolean
            4. Try parsing as datetime
            5. Return original string if no conversion possible
            
        **Output:**

            - int/float/bool/datetime/str: Converted value
    """
    try:
        if value.isdigit():
            return int(value)
        return float(value)
    except ValueError:
        if value.lower() in ["true", "false"]:
            return value.lower() == "true"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                days_since_epoch = float(value)
                return datetime(1899, 12, 30) + timedelta(days=days_since_epoch)
            except ValueError:
                return value

def check_username_exists(username: str) -> Optional[str]:
    """
        Check if username exists in Google Sheets.

        **Input:**

            - username (str): Username to check
            
        **Process:**

            1. Connect to Google Sheets service
            2. Fetch all usernames
            3. Search for matching username
            
        **Output:**

            - str: User ID if found
            - None: If username not found
            - HTTPException: 500 if Google Sheets error
    """
    try:
        sheets = get_google_sheets_service()
        # Fetch both columns A and B
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f'{USER_SHEET_RANGE}!A2:B').execute()
        values = result.get('values', [])
        
        for row in values:
            # Ensure the row has at least two columns (ID and username)
            if len(row) > 1 and row[1] == username:
                return row[0]  # Return the ID from column A
        
        return None  # Return None if the username doesn't exist
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

## Password Helper
def hash_password(password: str) -> str:
    """
        Hash password using bcrypt.

        **Input:**

            - password (str): Plain text password
            
        **Process:**

            1. Generate salt
            2. Hash password with salt
            3. Return encoded hash
            
        **Output:**

            - str: Hashed password
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
        Verify password against hashed version.

        **Input:**

            - plain_password (str): Password to verify
            - hashed_password (str): Stored hashed password
            
        **Process:**

            1. Hash plain password
            2. Compare with stored hash
            
        **Output:**

            - bool: True if password matches, False otherwise
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

## JWT Helper
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
        Create JWT access token.

        **Input:**

            - data (dict): Token payload data
            - expires_delta (timedelta, optional): Token expiration time
            
        **Process:**

            1. Copy input data
            2. Add expiration to payload
            3. Generate JWT token
            
        **Output:**

            - str: Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Update the require_level function to use FastAPIRequest
def require_level(min_level: int):
    def dependency(request: Request): # เปลี่ยนเป็น Request เพื่อเข้าถึง .cookies
        token = request.cookies.get("access_token")
        print(f"Token from cookie: {token}")
        if not token:
            # ถ้าไม่มี token ให้ redirect ไปหน้าแรกของ frontend
            # คุณอาจต้องเปลี่ยน URL นี้ให้เป็น URL จริงของหน้าแรก frontend ของคุณ
            return RedirectResponse(url="/", status_code=302)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            print(f"Decoded payload: {payload}")
            user_data = payload.get("user_data")
            if not user_data or "level" not in user_data:
                # ถ้าข้อมูล token ไม่ถูกต้อง ก็ redirect
                return RedirectResponse(url="/", status_code=302)
            user_level = int(user_data["level"])
            print(f"User level: {user_level}, Required level: {min_level}")
            if user_level < min_level:
                # ถ้า level ไม่ถึง ก็ redirect
                return RedirectResponse(url="/", status_code=302)
        except jwt.ExpiredSignatureError as e:
            print(f"Token expired error: {e}")
            # ถ้า token หมดอายุ ก็ redirect
            return RedirectResponse(url="/", status_code=302)
        except jwt.InvalidTokenError as e:
            print(f"Invalid token error: {e}")
            # ถ้า token ไม่ถูกต้อง ก็ redirect
            return RedirectResponse(url="/", status_code=302)
    return dependency

# === Routes ===

# 7. POST Login and Generate Token
@router.post("/login")
async def login(user: Dict[str, Any], response: Response):
    """
        Authenticate user and generate token.

        **Input:**

            - user (Dict[str, Any]): Login credentials
            
        **Process:**

            1. Validate credentials
            2. Verify password
            3. Generate access token
            4. Prepare user response data
            
        **Output:**

            - Dict: Token and user data
            - HTTPException: 401 if authentication fails
            - HTTPException: 500 if Google Sheets error
    """
    print(f"User data: {user}")
    if not user.get("username") or not user.get("password"):
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        
        headers = values[0]  # ใช้ row แรกเป็น headers
        for row in values[1:]:  # เริ่มจาก row ที่ 2
            user_data = dict(zip(headers, [convert_value(value) for value in row]))
            if user_data.get("username") == user["username"]:
                # ตรวจสอบ password
                if not verify_password(user["password"], user_data.get("password")):
                    raise HTTPException(status_code=401, detail="Invalid password")
                
                                # กำหนด response fields
                response_user = {
                    "id": user_data.get("id"),
                    "username": user_data.get("username"),
                    "name": user_data.get("name"),
                    "department": user_data.get("department"),
                    "position": user_data.get("position"),
                    "level": user_data.get("level")
                }

                # สร้าง JWT token
                token = create_access_token(data={"sub": user_data.get("id"), "user_data": response_user})
                
                                # ✅ Set token in HTTP-only cookie
                response.set_cookie(
                    key="access_token",
                    value=token,
                    httponly=True,
                    max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert minutes to seconds
                    secure=True,
                    samesite="None",
                )


                return {
                    "user": response_user,
                    "token_type": "httpOnlyCookie"
                }
        
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

## Get All Users
@router.get("/", response_model=List[Dict[str, Any]])
async def read_users(_: None = Depends(require_level(3))):
    """
        Retrieve all users from Google Sheets.

        **Input:**

            None (HTTP GET request)
            
        **Process:**

            1. Connect to Google Sheets service
            2. Fetch all rows from user sheet
            3. Convert values to appropriate types
            4. Map rows to dictionaries
            
        **Output:**

            - List[Dict]: List of user dictionaries
            - HTTPException: 404 if no users found
            - HTTPException: 500 if Google Sheets error
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]
        return [dict(zip(headers, map(convert_value, row))) for row in values[1:]]
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

## Get User by ID


## Create User
@router.post("/")
async def create_user(user: Dict[str, Any]):
    """
        Create new user in Google Sheets.

        **Input:**

            - user (Dict[str, Any]): User data in dictionary format
            
        **Process:**

            1. Check if username already exists
            2. Generate UUID for new user
            3. Add creation timestamp
            4. Convert user data to row format
            5. Append row to Google Sheets
            
        **Output:**

            - Dict: Success message with new user ID
            - HTTPException: 400 if username exists
            - HTTPException: 500 if Google Sheets error occurs
    """
    if check_username_exists(user.get("username")):
        raise HTTPException(status_code=400, detail="Username already exists")
    user["id"] = str(uuid4())
    user["createdOn"] = datetime.now().isoformat()
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        headers = result.get('values', [])[0]
        row_to_add = [user.get(header, "") for header in headers]
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=USER_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]}
        ).execute()
        return {"message": "User added successfully", "id": user["id"]}
    except HttpError:
        raise HTTPException(status_code=500, detail="Error writing to Google Sheets")

# 4. PUT Update User By ID
@router.put("/{user_id}")
async def update_user(user_id: str, updated_data: Dict[str, Any],_: None = Depends(require_level(1))):
    """
        Update existing user by ID.

        **Input:**

            - user_id (str): UUID of user to update
            - updated_data (Dict[str, Any]): New user data
            
        **Process:**

            1. Find user row in Google Sheets
            2. Merge existing data with updates
            3. Convert updated data to row format
            4. Execute update in Google Sheets
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if user not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]
        for i, row in enumerate(values[1:], start=2):
            if row[0] == user_id:
                updated_row = [updated_data.get(header, row[j]) for j, header in enumerate(headers)]
                sheets.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{USER_SHEET_RANGE}!A{i}",
                    valueInputOption="RAW",
                    body={"values": [updated_row]}
                ).execute()
                return {"message": "User updated successfully"}
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error updating Google Sheets")

# 5. DELETE User By ID
@router.delete("/{user_id}")
async def delete_user(user_id: str,_: None = Depends(require_level(1))):
    """
        Delete user by ID from Google Sheets.

        **Input:**

            - user_id (str): UUID of user to delete
            
        **Process:**

            1. Find user row in Google Sheets
            2. Delete entire row using batch update
            3. Execute deletion operation
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if user not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        for i, row in enumerate(values[1:], start=2):
            if row[0] == user_id:
                sheets.values().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body={"requests": [{"deleteDimension": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "ROWS",
                            "startIndex": i - 1,
                            "endIndex": i
                        }
                    }}]}
                ).execute()
                return {"message": "User deleted successfully"}
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error deleting from Google Sheets")

# 6. POST Register User with Password Hashing
@router.post("/register")
async def register_user(user: Dict[str, Any]):
    """
        Register new user with password hashing.

        **Input:**

            - user (Dict[str, Any]): User registration data
            
        **Process:**

            1. Validate required fields
            2. Check username availability
            3. Hash password
            4. Generate user ID and timestamp
            5. Save to Google Sheets
            
        **Output:**

            - Dict: Success message with user ID
            - HTTPException: 400 if validation fails
            - HTTPException: 500 if Google Sheets error
    """
    if not user.get("username") or not user.get("password"):
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    if check_username_exists(user.get("username")):
        raise HTTPException(status_code=400, detail="Username already exists")
    
    hashed_password = hash_password(user["password"])
    user_id = str(uuid4())
    created_on = datetime.now().isoformat()
    
    user["id"] = user_id
    user["createdOn"] = created_on
    user["password"] = hashed_password  # Save hashed password
    user["level"] = 1

    try:
        sheets = get_google_sheets_service()
        
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values or not values[0]:
            raise HTTPException(status_code=500, detail="Header row is missing in the sheet")
        
        headers = values[0]
        row_to_add = [user.get(header, "") for header in headers]
        
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=USER_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]}
        ).execute()
        
        return {"message": "User registered successfully", "id": user_id}
    except HttpError:
        raise HTTPException(status_code=500, detail="Error writing to Google Sheets")



# @router.get("/google_signup")
# async def google_signup(code: str = Query(...)):
#     """
#         Handle Google OAuth2 signup/login flow.

#         **Input:**

#             - code (str): Authorization code from Google
            
#         **Process:**

#             1. Exchange code for access token
#             2. Verify ID token
#             3. Check if user exists
#             4. Create new user if needed
#             5. Generate access token
            
#         **Output:**

#             - RedirectResponse: Redirect with token
#             - HTTPException: Various error cases
#     """
#     try:
#         # **ขั้นตอนที่ 1: รับ token access จาก Google ด้วย code**
#         token_url = "https://oauth2.googleapis.com/token"
#         client_id = "58925176098-4s7j4uqgh9h77e1n74af32kt1spfml89.apps.googleusercontent.com"   #! ควรเก็บใน ENV
#         client_secret = "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"   #! ควรเก็บใน ENV
#         redirect_uri = "http://localhost:8000/users/google_signup"  

#         data = {
#             "code": code,
#             "client_id": client_id,
#             "client_secret": client_secret,
#             "redirect_uri": redirect_uri,
#             "grant_type": "authorization_code",
#         }

#         token_response = requests.post(token_url, data=data)
#         token_response.raise_for_status()
#         tokens = token_response.json()
#         id_token = tokens.get("id_token")

#         if not id_token:
#             raise HTTPException(status_code=400, detail="ID Token missing in response")

#         # **ขั้นตอนที่ 2: Decode ID Token เพื่อดึงข้อมูล email**
#         id_info = verify_oauth2_token(id_token, GoogleRequest(), client_id)
#         email = id_info.get("email")
#         if not email:
#             raise HTTPException(status_code=400, detail="Email not found in ID Token")

#         # **ขั้นตอนที่ 3: ตรวจสอบว่า email มีอยู่ใน Google Sheets หรือไม่**
#         existsId = check_username_exists(email)

#         if existsId:
#             access_token = create_access_token(data={"sub": existsId})
#             redirect_url = f"http://localhost:3000/monitortoken?token={access_token}&username={email}"  #! แก้ urlfrontend
#             return RedirectResponse(url=redirect_url)

#         # **ขั้นตอนที่ 4: เพิ่ม email ลงใน Google Sheets**
#         user_data = {
#             "id": str(uuid4()),
#             "username": email,
#             "level" : 1,
#             "createdOn": datetime.now().isoformat(),
#         }

#         sheets = get_google_sheets_service()
#         result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
#         headers = result.get('values', [])[0]

#         row_to_add = [user_data.get(header, "") for header in headers]
#         sheets.values().append(
#             spreadsheetId=SPREADSHEET_ID,
#             range=USER_SHEET_RANGE,
#             valueInputOption="RAW",
#             body={"values": [row_to_add]},
#         ).execute()

#         access_token = create_access_token(data={"sub": user_data["id"]})

#         redirect_url = f"http://localhost:3000/assets?token={access_token}"#! แก้ urlfrontend

#         return RedirectResponse(url=redirect_url)
#     except requests.RequestException as e:
#         raise HTTPException(status_code=500, detail=f"Error communicating with Google: {e}")
#     except HttpError:
#         raise HTTPException(status_code=500, detail="Error writing to Google Sheets")
    

@router.get("/{user_id}", response_model=Dict[str, Any],)
async def get_user_by_id(user_id: str,_: None = Depends(require_level(1))):
    """
        Retrieve user by ID from Google Sheets.

        **Input:**

            - user_id (str): UUID of user to retrieve
            
        **Process:**

            1. Connect to Google Sheets service
            2. Find user row by ID
            3. Convert row data to dictionary format
            
        **Output:**

            - Dict: User data dictionary
            - HTTPException: 404 if user not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")

        headers = values[0]
        for row in values[1:]:
            if row[0] == user_id:
                return dict(zip(headers, map(convert_value, row)))
        
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")
    
@router.post("/reset_password")
async def reset_password(request: Dict[str, Any],_: None = Depends(require_level(1))):
    """
        Reset user password.

        **Input:**

            - request (Dict[str, Any]): Password reset data
                - user_id: User ID
                - old_password: Current password
                - new_password: New password
            
        **Process:**

            1. Validate input data
            2. Find user in Google Sheets
            3. Verify old password
            4. Hash and update new password
            
        **Output:**

            - Dict: Success/failure message
            - HTTPException: 400 if validation fails
            - HTTPException: 404 if user not found
            - HTTPException: 500 if Google Sheets error
    """
    user_id = request.get("user_id")
    old_password = request.get("old_password")
    new_password = request.get("new_password")
    
    if not user_id or not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    try:
        # Fetch all user data from the Google Sheet
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No user data found")
        
        headers = values[0]  # Header row
        for i, row in enumerate(values[1:], start=2):  # Data rows, start index at 2 for row number
            user_data = dict(zip(headers, row))
            if user_data.get("id") == user_id:
                if not verify_password(old_password, user_data.get("password", "")):
                    return {"message": "Password not updated"}  # Do not specify reason
                
                hashed_new_password = hash_password(new_password)
                user_data["password"] = hashed_new_password
                
                updated_row = [user_data.get(header, row[j]) for j, header in enumerate(headers)]
                sheets.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{USER_SHEET_RANGE}!A{i}",
                    valueInputOption="RAW",
                    body={"values": [updated_row]}
                ).execute()
                
                return {"message": "Password updated successfully"}
        
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Error updating password: {e}")

@router.post("/logout")
async def logout(response: Response,_: None = Depends(require_level(1))):
    # To delete a cookie, set it with an expired max_age
    response.delete_cookie(key="access_token", value="", max_age=0, path="/")
    return {"message": "Logged out successfully, token cookie deleted"}