"""
asset.py
--------
A FastAPI module for managing assets in a Google Sheets document.
"""
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
""" credentials file declared in the Google Cloud Platform """
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
ASSET_SHEET_RANGE = 'Asset'  #! ระบุช่วงข้อมูลใน Google Sheet สำหรับ Asset
""" name of google sheet page """
HEADERS = ["MACADDRESS", "TimeStamp (Last)", "Playbox Label", "Store Location", "Store Section", "StoreCode", "RUNNO(Some)", "GroupID", "GroupName", "TimeStamp (Last Run)", "Black Condition", "Retailer", "Category", "DisplayConnected", "Display AspectRatio", "Display Arrangement", "Display Position", "ConnectVia", "wifiSSID", "ProjectName", "screen Position Side", "setMacAddress", "Phone", "DongleWifi", "id", "isDelete", "createdOn"];
""" list of headers in the Google Sheets document same as key of json file """

router = APIRouter()

# === Helper Functions ===

def get_google_sheets_service():
    """Initialize the Google Sheets service."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def convert_value(value: str):
    """Convert string values to their appropriate Python types such as int, float, bool, or datetime."""
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
    """input is a list of values and a target string to search for. The function performs a binary search on the values and returns the row number (1-based) if found, otherwise -1.

    Args:
        values (list): rows of values from Google Sheets
        target (str): the target string to search for

    Returns:
        int: the row number (1-based) if found, otherwise -1
    """
    if not values or len(values) < 2:
        return -1  # Handle cases with no data or just a header

    # Extract and sort rows (excluding the header) based on the UUID in the first column
    sorted_values = sorted(values[1:], key=lambda row: row[0].strip().lower())

    normalized_view_id = target.strip().lower()
    low, high = 0, len(sorted_values) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_value = sorted_values[mid][0].strip().lower()

        if mid_value == normalized_view_id:
            # Find the original index in the unsorted list
            original_index = values.index(sorted_values[mid])
            return original_index + 1  # +1 to make it 1-based
        elif mid_value < normalized_view_id:
            low = mid + 1
        else:
            high = mid - 1

    return -1  # Not found

# === CRUD Routes for Asset ===

@router.get("/", response_model=List[Dict[str, Any]])
async def read_assets():
    """ Summary: Read all assets from the Google Sheets document.
        flow: get_google_sheets_service() -> sheets.values().get() -> parse_value() -> data
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        values = result.get("values", [])
        if not values:
            raise HTTPException(status_code=404, detail="No views found")
        
        headers = values[0]  # First row as headers
        
        def parse_value(value):
            try:
                # Attempt to parse as JSON
                return json.loads(value)
            except (ValueError, TypeError):
                # If value is "1" or "0", convert to int
                if value == "1":
                    return 1
                elif value == "0":
                    return 0
                return value  # Return as string if not JSON

        # Parse rows into dictionaries
        data = [
            {headers[i]: parse_value(cell) for i, cell in enumerate(row)}
            for row in values[1:]
        ]
        
        # Exclude views where isDelete is 1
        return [view for view in data if view.get("isDelete") != 1]
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.post("/")
async def create_asset(asset: Dict[str, Any]):
    """ Summary: Create a new asset in the Google Sheets document.
        Flow: input asset dict -> set id, createdOn, isDelete -> sheets.values().append() -> success message
    """
    asset["id"] = str(uuid4())
    asset["createdOn"] = datetime.now().isoformat()
    asset["isDelete"] = 0  # Default to not deleted
    try:
        sheets = get_google_sheets_service()
        row_to_add = [asset.get(header, "") for header in HEADERS]
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
    """Summary: Update an existing asset by ID.
        Flow: get_google_sheets_service() -> sheets.values().get() -> binary_search_by_index() -> update values -> sheets.values().batchUpdate()"""
    try:
        # Initialize Google Sheets service
        sheets = get_google_sheets_service()

        # Determine the column index for "id"
        if "id" not in HEADERS:
            raise HTTPException(status_code=500, detail="ID column not defined in headers")
        id_column_index = HEADERS.index("id") + 1  # 1-based index for Google Sheets
        id_column_letter = chr(64 + id_column_index)  # Convert index to column letter

        # Fetch the "id" column dynamically
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"{ASSET_SHEET_RANGE}!{id_column_letter}:{id_column_letter}"
        ).execute()
        values = result.get("values", [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        row_number = binary_search_by_index(values, asset_id)
        if row_number == -1:
            raise HTTPException(status_code=404, detail="Asset not found")
        updates = []
        for header, value in updated_data.items():
            if header in HEADERS:
                col_index = HEADERS.index(header) + 1
                updates.append({
                    "range": f"{ASSET_SHEET_RANGE}!{chr(64 + col_index)}{row_number}",
                    "values": [[str(value)]]
                })
        if updates:
            sheets.values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"data": updates, "valueInputOption": "RAW"}).execute()
        return {"message": "Asset updated successfully"}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Summary: Mark an asset as deleted by setting isDelete to 1.
        Flow: get_google_sheets_service() -> sheets.values().get() -> binary_search_by_index() -> sheets.values().update()"""
    try:
        # Initialize Google Sheets service
        sheets = get_google_sheets_service()

        # Determine the column index for "id"
        if "id" not in HEADERS:
            raise HTTPException(status_code=500, detail="ID column not defined in headers")
        id_column_index = HEADERS.index("id") + 1  # 1-based index for Google Sheets
        id_column_letter = chr(64 + id_column_index)  # Convert index to column letter

        # Fetch the "id" column dynamically
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"{ASSET_SHEET_RANGE}!{id_column_letter}:{id_column_letter}"
        ).execute()
        values = result.get("values", [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")
        row_number = binary_search_by_index(values, asset_id)
        if row_number == -1:
            raise HTTPException(status_code=404, detail="Asset not found")
        col_index = HEADERS.index("isDelete") + 1
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSET_SHEET_RANGE}!{chr(64 + col_index)}{row_number}",
            valueInputOption="RAW",
            body={"values": [[1]]}
        ).execute()
        return {"message": "Asset marked as deleted"}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")



