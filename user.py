from fastapi import APIRouter, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import bcrypt
import jwt
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends

# Configuration
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'
USER_SHEET_RANGE = 'User'

# JWT Config
SECRET_KEY = "omgthailand"  # ควรเก็บไว้ใน ENV
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()

# Helper Functions
def get_google_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def convert_value(value: str):
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                days_since_epoch = float(value)
                return datetime(1899, 12, 30) + timedelta(days=days_since_epoch)
            except ValueError:
                pass
        return value

def check_username_exists(username: str) -> bool:
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f'{USER_SHEET_RANGE}!B2:B').execute()
        values = result.get('values', [])
        
        for row in values:
            if row and row[0] == username:
                return True
        return False
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# Helper Functions for Password Hashing
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Helper Functions for Token
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Routes

# 1. GET All Users
@router.get("/", response_model=List[Dict[str, Any]])
async def read_users():
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]
        return [dict(zip(headers, [convert_value(value) for value in row])) for row in values[1:]]
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# 2. GET User By ID
@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user_by_id(user_id: str):
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=USER_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]
        for row in values[1:]:
            user_data = dict(zip(headers, [convert_value(value) for value in row]))
            if user_data.get("id") == user_id:  # Assuming "id" is the column name
                return user_data
        raise HTTPException(status_code=404, detail="User not found")
    except HttpError:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# 3. POST Create User
@router.post("/")
async def create_user_with_check(user: Dict[str, Any]):
    if not user.get("username"):
        raise HTTPException(status_code=400, detail="Username is required")

    if check_username_exists(user.get("username")):
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user_id = str(uuid4())
    created_on = datetime.now().isoformat()
    
    user["id"] = user_id
    user["createdOn"] = created_on
    
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
        
        return {"message": "User added successfully", "id": user_id}
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


# Protected Route Example
@router.get("/protected")
async def protected_route(token: str = Depends(oauth2_scheme)):
    username = verify_token(token)
    return {"message": f"Hello, {username}"}
