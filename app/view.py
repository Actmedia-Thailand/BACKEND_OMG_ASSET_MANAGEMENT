"""
    View Management Module
    =====================

    This module provides a FastAPI router for managing views in a Google Sheets document.
    It implements CRUD operations for view management.

    **Features**

        * Google Sheets integration for view data storage
        * Binary search implementation for efficient view lookup
        * JSON data handling for complex view configurations
        * Soft delete functionality
        * Batch update operations

    **API Endpoints**

        * GET /: Retrieve all non-deleted views
        * POST /: Create new view
        * PUT /{view_id}: Update existing view
        * DELETE /{view_id}: Soft delete view

    **Configuration**

        * Uses Google Sheets API v4
        * Configurable sheet range and headers
        * Environment variables for sensitive data

    **Dependencies**

        * FastAPI: Web framework
        * google-auth: Google authentication
        * google-api-python-client: Google Sheets API client
"""

from fastapi import APIRouter, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from typing import List, Dict, Any
from uuid import uuid4
import json
import asyncio
from app.sheets_service import get_google_sheets_service

SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! Should be stored in ENV
VIEW_SHEET_RANGE = 'View'  #! Specify the range for the View sheet
HEADERS = ["id", "id_user", "data_type", "name", "levelView", "filters", "sorting", "group", "isDelete", "createdOn"]

router = APIRouter()

async def update_headers_from_sheet():
    """
        Fetch headers from the first row of Google Sheets and update HEADERS global variable.

        **Process:**
            1. Connect to Google Sheets service
            2. Fetch first row from specified range
            3. Update global HEADERS variable with new values
            
        **Output:**
            None (updates global HEADERS)
    """
    global HEADERS
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"{VIEW_SHEET_RANGE}!1:1"  # Fetch only first row
        ).execute()
        values = result.get("values", [])
        if not values or not values[0]:
            print("No headers found in Google Sheets")
            return
        
        # Update HEADERS with values from first row
        HEADERS = [header.strip() for header in values[0] if header]  # Remove empty headers and strip whitespace
        print(f"Updated HEADERS: {HEADERS}")
    except HttpError as e:
        print(f"Failed to update headers: {e}")

async def periodic_header_update():
    """
        Periodically update HEADERS every 10 minutes by calling update_headers_from_sheet.

        **Process:**
            1. Run infinite loop
            2. Call update_headers_from_sheet
            3. Wait 10 minutes before next iteration
            
        **Output:**
            None (runs continuously)
    """
    while True:
        await update_headers_from_sheet()
        await asyncio.sleep(21600)  # time to re-load in sec

# Start the periodic task when the application starts
@router.on_event("startup")
async def startup_event():
    """
        Start the periodic header update task when the FastAPI app starts.
    """
    asyncio.create_task(periodic_header_update())

# หรือเพิ่ม endpoint
@router.post("/update-headers")
async def manual_update_headers():
    await update_headers_from_sheet()
    return {"message": "Headers updated"}


def convert_value(value: str):
    """
        Convert string values to appropriate Python types.

        **Input:**

            - value (str): String value to convert from Google Sheets
            
        **Process:**

            1. Try converting to integer if string contains only digits
            2. Try converting to float if possible
            3. Convert to boolean if string is "true" or "false"
            4. Return stripped string if no conversion possible
            
        **Output:**

            - int: If value is numeric integer
            - float: If value is numeric with decimal
            - bool: If value is boolean string
            - str: If no other conversion is possible
    """
    try:
        if value.isdigit():
            return int(value)
        return float(value)
    except ValueError:
        if value.lower() in ["true", "false"]:
            return value.lower() == "true"
        return value.strip()

def binary_search_by_index(values: list, target: str) -> int:
    """
        Perform binary search to find view row index.

        **Input:**

            - values (list): List of rows from Google Sheets
            - target (str): View ID to search for
            
        **Process:**

            1. Handle edge cases (empty list or single header)
            2. Sort values based on first column (excluding header)
            3. Perform binary search on sorted values
            4. Convert found index back to original row number
            
        **Output:**

            - int: Row number (1-based) if found
            - int: -1 if target not found
    """
    if not values or len(values) < 2:
        return -1  # Handle cases with no data or just a header

    sorted_values = sorted(values[1:], key=lambda row: row[0].strip().lower())
    normalized_view_id = target.strip().lower()
    low, high = 0, len(sorted_values) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_value = sorted_values[mid][0].strip().lower()

        if mid_value == normalized_view_id:
            original_index = values.index(sorted_values[mid])
            return original_index + 1  # +1 to make it 1-based
        elif mid_value < normalized_view_id:
            low = mid + 1
        else:
            high = mid - 1

    return -1

def parse_value(value):
    """
        Parse and convert cell values from Google Sheets.

        **Input:**

            - value (str): Raw value from Google Sheets cell
            
        **Process:**

            1. Try parsing as JSON for complex data types
            2. Convert "1" and "0" to integers
            3. Return original value if no conversion needed
            
        **Output:**

            - dict/list: If value is valid JSON
            - int: If value is "1" or "0"
            - str: Original value if no conversion applies
    """
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        if value == "1":
            return 1
        elif value == "0":
            return 0
        return value

@router.get("/", response_model=List[Dict[str, Any]])
async def read_views():
    """
        Retrieve all non-deleted views from Google Sheets.

        **Input:**

            None (HTTP GET request)
            
        **Process:**

            1. Connect to Google Sheets service
            2. Fetch all rows from specified range
            3. Parse values and convert to appropriate types
            4. Filter out deleted views
            
        **Output:**

            - List[Dict]: List of view dictionaries
            - HTTPException: 404 if no views found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=VIEW_SHEET_RANGE).execute()
        values = result.get("values", [])
        
        if not values:
            raise HTTPException(status_code=404, detail="No views found")
        
        headers = values[0]
        data = [
            {headers[i]: parse_value(cell) for i, cell in enumerate(row)}
            for row in values[1:]
        ]
        
        return [view for view in data if view.get("isDelete") != 1]
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.post("/")
async def create_view(view: Dict[str, Any]):
    """
        Create new view in Google Sheets.

        **Input:**

            - view (Dict[str, Any]): View data in dictionary format
            
        **Process:**

            1. Generate UUID for new view
            2. Add creation timestamp
            3. Set isDelete flag to 0
            4. Convert view dict to row format
            5. Append row to Google Sheets
            
        **Output:**

            - Dict: Success message with new view ID
            - HTTPException: 500 if Google Sheets error occurs
    """
    view["id"] = str(uuid4())
    view["isDelete"] = 0
    view["createdOn"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        sheets = get_google_sheets_service()
        row_to_add = [
            json.dumps(view[header]) if isinstance(view.get(header), list) else str(view.get(header, ""))
            for header in HEADERS
        ]
        
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
    """
        Update existing view by ID.

        **Input:**

            - view_id (str): UUID of view to update
            - updated_data (Dict[str, Any]): New view data
            
        **Process:**

            1. Find view row using binary search
            2. Create batch update operations for changed fields
            3. Convert complex data types to JSON strings
            4. Execute batch update in Google Sheets
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if view not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{VIEW_SHEET_RANGE}!A:A").execute()
        values = result.get("values", [])

        if not values or len(values) <= 1:
            raise HTTPException(status_code=404, detail="No views found")

        sheet_row_number = binary_search_by_index(values, view_id)
        if sheet_row_number == -1:
            raise HTTPException(status_code=404, detail="View ID not found")

        updates = []
        for header, value in updated_data.items():
            if header in HEADERS:
                col_index = HEADERS.index(header) + 1
                updates.append({
                    "range": f"{VIEW_SHEET_RANGE}!{chr(64 + col_index)}{sheet_row_number}",
                    "values": [[str(value)] if not isinstance(value, list) else [json.dumps(value)]]
                })

        if updates:
            body = {"data": updates, "valueInputOption": "RAW"}
            sheets.values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()

        return {"message": "View updated successfully"}

    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Failed to update Google Sheets: {e}")

@router.delete("/{view_id}")
async def delete_view(view_id: str):
    """
        Soft delete view by setting isDelete flag.

        **Input:**

            - view_id (str): UUID of view to delete
            
        **Process:**

            1. Find view row using binary search
            2. Update isDelete column to 1
            3. Execute update in Google Sheets
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if view not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{VIEW_SHEET_RANGE}!A:A").execute()
        values = result.get("values", [])

        if not values or len(values) <= 1:
            raise HTTPException(status_code=404, detail="No views found")

        sheet_row_number = binary_search_by_index(values, view_id)
        
        if sheet_row_number != -1:
            col_index = HEADERS.index("isDelete") + 1
            sheets.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{VIEW_SHEET_RANGE}!{chr(64 + col_index)}{sheet_row_number}",
                valueInputOption="RAW",
                body={"values": [[1]]}
            ).execute()
            
            return {"message": "View soft-deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="View not found")
    
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

