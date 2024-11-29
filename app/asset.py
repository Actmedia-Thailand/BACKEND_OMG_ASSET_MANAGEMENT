from fastapi import APIRouter, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import List, Dict, Any
from uuid import uuid4
import json

# === Configuration ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  #! ควรเก็บใน ENV
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
ASSET_SHEET_RANGE = 'Asset'  #! ระบุช่วงข้อมูลใน Google Sheet สำหรับ Asset
HEADERS = ["id", "firstName", "lastName", "gender", "age", "job_title", "salary", "start_date", "end_date", "isActive", "department", "address", "city", "country", "email", "phone_number", "createdOn"]

router = APIRouter()

# === Helper Functions ===

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

def binary_search_by_index(values: list, target: str) -> int:
    """Perform binary search on the values and return the row number (1-based) if found."""
    low, high = 0, len(values) - 1
    # Extract UUIDs from the rows, excluding the header
    uuids = [row[0].strip().lower() for row in values[1:] if row]  
    normalized_view_id = target.strip().lower()

    # Sort UUIDs before performing binary search
    sorted_indexes = sorted(range(len(uuids)), key=lambda i: uuids[i])

    while low <= high:
        mid = (low + high) // 2
        mid_index = sorted_indexes[mid]  # ใช้ index ที่จัดเรียงแล้ว
        mid_value = uuids[mid_index]

        if mid_value == normalized_view_id:
            return mid_index + 2  # +2 because the row is 1-based and the header is at row 1
        elif mid_value < normalized_view_id:
            low = mid + 1
        else:
            high = mid - 1

    return -1  # Not found

# === CRUD Routes for Asset ===

@router.get("/", response_model=List[Dict[str, Any]])
async def read_assets():
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
    asset["id"] = str(uuid4())  # Generate a unique ID for the asset
    asset["createdOn"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")  # Add the current timestamp
    try:
        sheets = get_google_sheets_service()
        
        # Align the new asset with the headers
        row_to_add = [asset.get(header, "") for header in HEADERS]
        
        # Append the new row to the sheet
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
        # เรียกใช้ Google Sheets API
        sheets = get_google_sheets_service()
        
        # ดึงเฉพาะคอลัมน์แรกจาก Google Sheets
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"{ASSET_SHEET_RANGE}!A:A"  # คอลัมน์แรกเท่านั้น
        ).execute()
        
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        
        # หาหมายเลขแถวที่ตรงกับ asset_id ด้วย binary_search_by_index
        sheet_row_number = binary_search_by_index(values, asset_id)
        if sheet_row_number == -1:
            raise HTTPException(status_code=404, detail="Asset ID not found")

        # เตรียมข้อมูลอัปเดต
        updates = []
        for header, value in updated_data.items():
            if header in HEADERS:  # ตรวจสอบว่า header อยู่ใน HEADERS
                col_index = HEADERS.index(header) + 1  # คำนวณเป็น 1-based index
                updates.append({
                    "range": f"{ASSET_SHEET_RANGE}!{chr(64 + col_index)}{sheet_row_number}",  # A1 notation
                    "values": [[str(value)] if not isinstance(value, list) else [json.dumps(value)]]
                })

        # ตรวจสอบว่ามีข้อมูลที่ต้องอัปเดตหรือไม่
        if updates:
            body = {"data": updates, "valueInputOption": "RAW"}
            sheets.values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()

        return {"message": "Asset updated successfully"}

    except HttpError as e:
        error_message = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to update Google Sheets: {error_message}")


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete an asset by ID using binary search."""
    try:
        # Get the Google Sheets service
        sheets = get_google_sheets_service()
        
        # Fetch only the UUID column
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID,range=f"{ASSET_SHEET_RANGE}!A:A").execute()
        values = result.get("values", [])

        if not values or len(values) <= 1:
            raise HTTPException(status_code=404, detail="No views found")

        # Perform binary search on values to find the correct row index
        sheet_row_number = binary_search_by_index(values, asset_id)
        
        # Delete the row using batchUpdate
        if sheet_row_number != -1:
            sheets.batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={"requests": [{
                    "deleteDimension": {
                        "range": {
                            "sheetId": 1133662521,  # Replace with the actual sheetId
                            "dimension": "ROWS",
                            "startIndex": sheet_row_number - 1,  # Subtract 1 to get the correct zero-based index
                            "endIndex": sheet_row_number
                        }
                    }
                }]}
            ).execute()
        
        return {"message": f"Asset with ID {asset_id} deleted successfully"}
    
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")



