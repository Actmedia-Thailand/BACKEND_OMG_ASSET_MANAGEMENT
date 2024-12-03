from fastapi import APIRouter, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from typing import List, Dict, Any
from uuid import uuid4
import json

# === Configuration ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  #! Should be stored in ENV
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! Should be stored in ENV
VIEW_SHEET_RANGE = 'View'  #! Specify the range for the View sheet
HEADERS = ["id", "id_user", "data_type", "name", "levelView", "filters", "sorting", "group", "isDelete", "createdOn"]

router = APIRouter()

# === Helper Functions ===

def get_google_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def convert_value(value: str):
    """Convert string values to their appropriate Python types."""
    try:
        if value.isdigit():
            return int(value)
        return float(value)
    except ValueError:
        if value.lower() in ["true", "false"]:
            return value.lower() == "true"
        return value.strip()
    
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



# === CRUD Routes for View ===

@router.get("/", response_model=List[Dict[str, Any]])
async def read_views():
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=VIEW_SHEET_RANGE).execute()
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
async def create_view(view: Dict[str, Any]):
    view["id"] = str(uuid4())  # Generate a unique ID
    view["isDelete"] = 0  # Default to not deleted
    view["createdOn"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")  # Current timestamp

    try:
        sheets = get_google_sheets_service()

        # Convert arrays to strings
        row_to_add = [
            json.dumps(view[header]) if isinstance(view.get(header), list) else str(view.get(header, ""))
            for header in HEADERS
        ]
        
        # Append to the sheet
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=VIEW_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]}
        ).execute()

        return {"message": "View created successfully", "id": view["id"]}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")



@router.put("/{view_id}")
async def update_view(view_id: str, updated_data: Dict[str, Any]):
    """Update an existing view by ID."""
    try:
        sheets = get_google_sheets_service()

        # Fetch only the ID column to locate the row number
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{VIEW_SHEET_RANGE}!A:A").execute()
        values = result.get("values", [])

        if not values or len(values) <= 1:
            raise HTTPException(status_code=404, detail="No views found")

        # Find the row that matches the view_id
        sheet_row_number = binary_search_by_index(values, view_id)
        if sheet_row_number == -1:
            raise HTTPException(status_code=404, detail="View ID not found")

        # Prepare updates for specific columns based on updated_data
        updates = []
        for header, value in updated_data.items():
            if header in HEADERS:
                col_index = HEADERS.index(header) + 1  # Convert to 1-based index for Google Sheets
                updates.append({
                    "range": f"{VIEW_SHEET_RANGE}!{chr(64 + col_index)}{sheet_row_number}",  # A1 notation
                    "values": [[str(value)] if not isinstance(value, list) else [json.dumps(value)]]
                })

        #? Batch update all the specified columns good for update multi cell rather than normal update
        if updates:
            body = {"data": updates, "valueInputOption": "RAW"}
            sheets.values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()

        return {"message": "View updated successfully"}

    except HttpError as e:
        error_message = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to update Google Sheets: {error_message}")


@router.delete("/{view_id}")
async def delete_view(view_id: str):
    """Soft-delete a view by ID."""
    try:
        sheets = get_google_sheets_service()
        
        # Fetch only the first column (IDs) from the sheet
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{VIEW_SHEET_RANGE}!A:A").execute()
        values = result.get("values", [])

        if not values or len(values) <= 1:
            raise HTTPException(status_code=404, detail="No views found")

        # Perform binary search on values to find the correct row index
        sheet_row_number = binary_search_by_index(values, view_id)
        
        # Update only the `isDelete` column for the row
        col_index = HEADERS.index("isDelete") + 1
        if sheet_row_number != -1:
            sheets.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{VIEW_SHEET_RANGE}!{chr(64 + col_index)}{sheet_row_number}",  # Assuming `isDelete` is in column I
                valueInputOption="RAW",
                body={"values": [[1]]}  # Set `isDelete` to 1 (soft delete)
            ).execute()
            
            return {"message": "View soft-deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="View not found")
    
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

