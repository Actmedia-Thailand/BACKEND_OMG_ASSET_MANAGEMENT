from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4
import requests
import bcrypt
import jwt

# === Configuration ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  #! ควรเก็บใน ENV
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
USER_SHEET_RANGE = 'User'

SECRET_KEY = "omgthailand"  #! ควรเก็บใน ENV
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()

# === Helper Functions ===

## Google Sheets Helper
def get_google_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def convert_value(value: str):
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
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

## JWT Helper
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# === Routes ===

## Get All Users
@router.get("/", response_model=List[Dict[str, Any]])
async def read_users():
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
async def update_user(user_id: str, updated_data: Dict[str, Any]):
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]
        for i, row in enumerate(values[1:], start=2):  # Start from 2 because row 1 is header
            if row[0] == user_id:  # Assuming "id" is in the first column
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
async def delete_user(user_id: str):
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        for i, row in enumerate(values[1:], start=2):  # Start from 2 because row 1 is header
            if row[0] == user_id:  # Assuming "id" is in the first column
                sheets.values().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body={"requests": [{"deleteDimension": {
                        "range": {
                            "sheetId": 0,  # Assuming first sheet
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
    user["permission"] = 1

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

# 7. POST Login and Generate Token
@router.post("/login")
async def login(user: Dict[str, Any]):
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
                
                # สร้าง JWT token
                token = create_access_token(data={"sub": user_data["id"]})
                
                # กำหนด response fields
                response_user = {
                    "id": user_data.get("id"),
                    "username": user_data.get("username"),
                    "name": user_data.get("name"),
                    "department": user_data.get("department"),
                    "position": user_data.get("position"),
                    "permission": user_data.get("permission")
                }
                
                return {
                    "access_token": token,
                    "user": response_user,
                    "token_type": "bearer"
                }
        
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

@router.get("/google_signup")
async def google_signup(code: str = Query(...)):
    try:
        # **ขั้นตอนที่ 1: รับ token access จาก Google ด้วย code**
        token_url = "https://oauth2.googleapis.com/token"
        client_id = "58925176098-4s7j4uqgh9h77e1n74af32kt1spfml89.apps.googleusercontent.com"   #! ควรเก็บใน ENV
        client_secret = "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"   #! ควรเก็บใน ENV
        redirect_uri = "http://localhost:8000/users/google_signup"  

        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        token_response = requests.post(token_url, data=data)
        token_response.raise_for_status()
        tokens = token_response.json()
        id_token = tokens.get("id_token")

        if not id_token:
            raise HTTPException(status_code=400, detail="ID Token missing in response")

        # **ขั้นตอนที่ 2: Decode ID Token เพื่อดึงข้อมูล email**
        id_info = verify_oauth2_token(id_token, Request(), client_id)
        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in ID Token")

        # **ขั้นตอนที่ 3: ตรวจสอบว่า email มีอยู่ใน Google Sheets หรือไม่**
        existsId = check_username_exists(email)

        if existsId:
            access_token = create_access_token(data={"sub": existsId})
            redirect_url = f"http://localhost:3000/assets?token={access_token}&username={email}"  #! แก้ urlfrontend
            return RedirectResponse(url=redirect_url)

        # **ขั้นตอนที่ 4: เพิ่ม email ลงใน Google Sheets**
        user_data = {
            "id": str(uuid4()),
            "username": email,
            "permission" : 1,
            "createdOn": datetime.now().isoformat(),
        }

        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        headers = result.get('values', [])[0]

        row_to_add = [user_data.get(header, "") for header in headers]
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=USER_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]},
        ).execute()

        access_token = create_access_token(data={"sub": user_data["id"]})

        redirect_url = f"http://localhost:3000/assets?token={access_token}"#! แก้ urlfrontend

        return RedirectResponse(url=redirect_url)
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Google: {e}")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error writing to Google Sheets")

@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user_by_id(user_id: str):
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")

        headers = values[0]  # ใช้ row แรกเป็น headers
        for row in values[1:]:  # เริ่มจาก row ที่ 2
            if row[0] == user_id:  # ตรวจสอบว่าค่าใน column แรกตรงกับ user_id
                return dict(zip(headers, map(convert_value, row)))  # ส่งข้อมูลกลับเป็น dict
        
        raise HTTPException(status_code=404, detail="User not found")  # หากไม่พบ user
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# Protected Route Example
@router.get("/protected")
async def protected_route(token: str = Depends(oauth2_scheme)):
    username = verify_token(token)
    return {"message": f"Hello, {username}"}
