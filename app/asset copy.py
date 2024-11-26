from fastapi import APIRouter, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from typing import List, Dict, Any
from uuid import uuid4

# === Configuration ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  #! ควรเก็บใน ENV
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
ASSET_SHEET_RANGE = 'Asset'  #! ระบุช่วงข้อมูลใน Google Sheet สำหรับ Asset
HEADERS = ["id", "First Name", "Last Name", "Gender", "Age", "Job Title", "Salary", "Start Date", "End Date", "Is Active", "Department", "Address", "City", "Country", "Email", "Phone Number", "createdOn"]


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
            
        # Perform Binary Search
def binary_search(data, target):
    low, high = 0, len(data) - 1
    while low <= high:
        mid = (low + high) // 2
        if data[mid] == target:
            return mid  # Return the index in the list
        elif data[mid] < target:
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
        
        # Fetch only the first row to get the headers
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"{ASSET_SHEET_RANGE}!A1:Z1"  # Adjust the range to cover only the header row
        ).execute()
        headers = result.get('values', [[]])[0]  # Get headers or an empty list if not present
        
        # Align the new asset with the headers
        row_to_add = [asset.get(header, "") for header in headers]
        
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
    """Update an existing asset by ID with minimal processing."""
    try:
        sheets = get_google_sheets_service()

        # Fetch UUID column (assuming "id" is in column A)
        uuids_result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, range=f"{ASSET_SHEET_RANGE}!A:A"
        ).execute()
        uuids = [row[0] for row in uuids_result.get("values", []) if row]

        # Find the row index using binary search
        row_index = binary_search(uuids, asset_id)
        if row_index == -1:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")

        # Construct the updated row
        updated_row = [updated_data.get(header, "") for header in HEADERS]

        # Update the specific row in Google Sheets
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSET_SHEET_RANGE}!A{row_index + 1}",  # +1 for 1-based indexing
            valueInputOption="RAW",
            body={"values": [updated_row]},
        ).execute()

        return {"message": f"Asset with ID {asset_id} updated successfully"}

    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")



@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete an asset by ID using binary search."""
    try:
        # Get the Google Sheets service
        sheets = get_google_sheets_service()
        
        # Fetch only the UUID column
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSET_SHEET_RANGE}!A:A"  # Assuming UUIDs are in column A
        ).execute()
        values = result.get("values", [])
        
        # Flatten the list of values
        uuids = [row[0] for row in values if row]  # Handle empty rows
        
        # Find the row index
        row_index = binary_search(uuids, asset_id)
        if row_index == -1:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")
        
        # Delete the row using batchUpdate
        sheets.batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": 1133662521,  # Replace with the actual sheetId
                        "dimension": "ROWS",
                        "startIndex": row_index,  # row_index corresponds to the sheet's row
                        "endIndex": row_index + 1
                    }
                }
            }]}
        ).execute()
        
        return {"message": f"Asset with ID {asset_id} deleted successfully"}
    
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")


