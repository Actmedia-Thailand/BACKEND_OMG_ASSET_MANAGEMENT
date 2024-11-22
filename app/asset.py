from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from typing import List, Dict, Any
from uuid import uuid4

# === Configuration ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  #! ควรเก็บใน ENV
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
ASSET_SHEET_RANGE = 'Asset'  #! ระบุช่วงข้อมูลใน Google Sheet สำหรับ Asset

router = APIRouter()

# === Helper Functions ===

def get_google_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def convert_value(value: str):
    try:
        return int(value) if value.isdigit() else float(value)
    except ValueError:
        return value

# === CRUD Routes for Asset ===

@router.get("/", response_model=List[Dict[str, Any]])
async def read_assets():
    """Retrieve all assets from the Google Sheet."""
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        headers = values[0]
        return [dict(zip(headers, map(convert_value, row))) for row in values[1:]]
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.post("/")
async def create_asset(asset: Dict[str, Any]):
    """Add a new asset to the Google Sheet."""
    asset["id"] = str(uuid4())
    asset["createdOn"] = datetime.now().isoformat()
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        headers = result.get('values', [])[0]
        row_to_add = [asset.get(header, "") for header in headers]
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=ASSET_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]}
        ).execute()
        return {"message": "Asset created successfully", "id": asset["id"]}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.put("/{asset_id}")
async def update_asset(asset_id: str, updated_data: Dict[str, Any]):
    """Update an existing asset by ID."""
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        headers = values[0]
        for i, row in enumerate(values[1:], start=2):
            if row[0] == asset_id:  # Assuming "id" is in the first column
                updated_row = [updated_data.get(header, row[j]) for j, header in enumerate(headers)]
                sheets.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{ASSET_SHEET_RANGE}!A{i}",
                    valueInputOption="RAW",
                    body={"values": [updated_row]}
                ).execute()
                return {"message": "Asset updated successfully"}
        raise HTTPException(status_code=404, detail="Asset not found")
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete an asset by ID."""
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        for i, row in enumerate(values[1:], start=2):
            if row[0] == asset_id:  # Assuming "id" is in the first column
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
                return {"message": "Asset deleted successfully"}
        raise HTTPException(status_code=404, detail="Asset not found")
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")
