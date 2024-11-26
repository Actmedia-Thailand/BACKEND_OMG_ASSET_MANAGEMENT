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
HEADERS = ["id", "id_user", "data_type", "viewName", "levelView", "filter", "group", "sort", "isDelete", "createdOn"]

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
    
def binary_search_by_index(data: list, target: str, indexes: list) -> int:
    low, high = 0, len(data) - 1
    while low <= high:
        mid = (low + high) // 2
        mid_index = indexes[mid]  # ใช้ดัชนีของแถวที่จัดเรียงแล้ว
        mid_value = data[mid_index]  # ใช้ค่าในตำแหน่งที่ดัชนี mid ชี้ไป
        print(f"Low: {low}, High: {high}, Mid: {mid}, Mid_index: {mid_index}, Mid_value: {mid_value}, Target: {target}")
        
        if mid_value == target:
            return mid_index  # Return the index of the original UUID
        elif mid_value < target:
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
        
        # Fetch the data from the sheet
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=VIEW_SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No views found")
        
        headers = values[0]  # The first row contains the headers
        
        # Find the row that matches the view_id (assuming "id" is in the first column)
        row_index = None
        for i, row in enumerate(values[1:], start=2):  # Skip header row, start at row 2
            if row[0] == view_id:  # View ID matches
                row_index = i
                break
        
        if row_index is None:
            raise HTTPException(status_code=404, detail="View not found")
        
        # Prepare the updated row data
        updated_row = []
        for j, header in enumerate(headers):
            # If the updated data has a value for the header, use it, otherwise keep the original
            updated_value = updated_data.get(header, values[row_index-1][j])  # Use the original value if not updated
            
            # Convert list values to string before updating
            if isinstance(updated_value, list):
                updated_value = json.dumps(updated_value)  # Convert the list as a JSON string
            updated_row.append(str(updated_value))  # Ensure the value is a string
        
        # Update the row in the sheet
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{VIEW_SHEET_RANGE}!A{row_index}",
            valueInputOption="RAW",
            body={"values": [updated_row]}
        ).execute()

        return {"message": "View updated successfully"}
    
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")


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

        # Extract UUIDs and generate indexes of the rows (1-based index)
        uuids = [row[0].strip().lower() for row in values[1:] if row]  # Excluding the header
        normalized_view_id = view_id.strip().lower()

        # Create an index list that tracks original positions of the UUIDs in the sorted order
        indexes = list(range(len(uuids)))
        indexes.sort(key=lambda x: uuids[x])  # Sort based on the UUID values
        

        # Perform binary search on indexes
        row_index = binary_search_by_index(uuids, normalized_view_id, indexes)
        
        if row_index == -1:
            raise HTTPException(status_code=404, detail="View not found")
        
        # Calculate row number in the sheet (add 2 for header and 1-based index)
        sheet_row_number = row_index + 2  # +2 เนื่องจาก index เริ่มที่ 0 และ Header อยู่ที่แถวที่ 1
        
        # Update only the `isDelete` column for the row
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{VIEW_SHEET_RANGE}!I{sheet_row_number}",  # Assuming `isDelete` is in column I
            valueInputOption="RAW",
            body={"values": [[1]]}  # Set `isDelete` to 1 (soft delete)
        ).execute()
        
        return {"message": "View soft-deleted successfully"}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")
