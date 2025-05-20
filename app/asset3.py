"""
    Asset Management Module
    ======================

    This module provides a FastAPI router for managing assets in a Google Sheets document.
    It implements CRUD operations for asset management.

    **Features**

        * Google Sheets integration for data storage
        * Binary search implementation for efficient asset lookup
        * Soft delete functionality
        * Automatic UUID generation for new assets
        * Type conversion utilities for Google Sheets data

    **API Endpoints**

        * GET /: Retrieve all non-deleted assets
        * POST /: Create a new asset
        * PUT /{asset_id}: Update an existing asset
        * DELETE /{asset_id}: Soft delete an asset

    **Configuration**

        * Uses Google Sheets API v4
        * Requires service account credentials
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
from datetime import datetime, timedelta
from typing import List, Dict, Any
from uuid import uuid4
import json
import asyncio
from app.sheets_service import get_google_sheets_service
from cachetools import TTLCache
from collections import defaultdict

# === Configuration ===
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  #! ควรเก็บใน ENV
ASSET_SHEET_RANGE = 'Asset2'  #! ระบุช่วงข้อมูลใน Google Sheet สำหรับ Asset
""" name of google sheet page """
HEADERS = ["id", "QR Code", "MACADDRESS", "assetTypeId", "Asset Name", "Category", "lastPlayerCommsMillis", "label", "storeLocation", "storeSection", "storeCode", "runNumber", "GroupID", "GroupName", "blackCondition", "retailer", "signageCategoryNameLocalised", "displaysConnected", "displayAspectRatio", "displayArrangement", "displayPosition", "ConnectVia", "wifiSsid", "ProjectName", "screen Position Side", "setMacAddress", "Phone", "DongleWifi", "Asset name","parentId","isDelete"]
""" list of headers in the Google Sheets document same as key of json file """

router = APIRouter()

# === Helper Functions ===

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
            range=f"{ASSET_SHEET_RANGE}!1:1"  # Fetch only first row
        ).execute()
        values = result.get("values", [])
        if not values or not values[0]:
            print("No headers found in Google Sheets")
            return
        
        # Update HEADERS with values from first row
        HEADERS = [header.strip() for header in values[0] if header]  # Remove empty headers and strip whitespace
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

            - value (str): String value to convert
            
        **Process:**

            1. Try converting to integer if string contains only digits
            2. Try converting to float if possible
            3. Try converting to boolean if string is "true" or "false"
            4. Return stripped string if no conversion possible
            
        **Output:**

            - int/float/bool/str: Converted value based on input type
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


def binary_search_by_index(values: list, target: str) -> int:
    """
        Perform binary search on Google Sheets values to find target asset.

        **Input:**

            - values (list): List of rows from Google Sheets
            - target (str): Asset ID to search for
            
        **Process:**

            1. Sort values based on first column (excluding header)
            2. Perform binary search on sorted values
            3. Convert found index back to original row number
            
        **Output:**

            - int: Row number (1-based) if found, -1 if not found
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

def get_column_letter(col_index: int) -> str:
    """Convert column index to Google Sheets column letter (A, B, ..., Z, AA, AB, ...)"""
    col_letter = ""
    while col_index > 0:
        col_index, remainder = divmod(col_index - 1, 26)
        col_letter = chr(65 + remainder) + col_letter
    return col_letter


# === CRUD Routes for Asset ===

# In-memory cache 
cache = TTLCache(maxsize=1, ttl=21600)  # Cache สูงสุด 1 item, หมดอายุใน 6 ชั่วโมง

@router.get("/", response_model=List[Dict[str, Any]])
async def read_assets():
    """
    Retrieve all non-deleted assets from Google Sheets as a tree structure.

    Process:
        1. Check cache
        2. Fetch data from Google Sheets
        3. Parse values
        4. Filter out deleted nodes and children of deleted parents
        5. Build children_map (parentId -> list of children)
        6. Recursively build tree from children_map
        7. Cache and return tree
    """

    if "assets" in cache:
        print("Cache hit")
        return cache["assets"]
    print("Reading from Google Sheets")
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=ASSET_SHEET_RANGE).execute()
        values = result.get("values", [])
        if not values:
            raise HTTPException(status_code=404, detail="No assets found")

        headers = values[0]

        def parse_value(value):
            if value == "1":
                return 1
            if value == "0":
                return 0
            if value is None:
                return ""
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return json.dumps(parsed, ensure_ascii=False)
                    return parsed
                except (ValueError, TypeError):
                    return value
            return str(value)

        data = [
            {headers[i]: parse_value(cell) for i, cell in enumerate(row) if i < len(headers)}
            for row in values[1:]
        ]

        # สร้าง map id->node เพื่อเช็ค parent later
        nodes_map = {node["id"]: node for node in data}

        # กำหนดค่า default และแก้ไข parentId ถ้า parent ถูกลบ
        for node in data:
            node.setdefault("isDelete", 1)
            node.setdefault("parentId", "")
            if node["parentId"]:
                parent = nodes_map.get(node["parentId"], {})
                if parent.get("isDelete", 1) == 1:
                    node["parentId"] = ""

        # สร้าง children_map: parentId -> list of child nodes
        children_map = defaultdict(list)
        for node in data:
            if node["isDelete"] == 0:
                children_map[node["parentId"]].append(node)

        # ฟังก์ชันสร้าง tree จาก children_map
        def build_tree(parent_id=""):
            tree = []
            for node in children_map.get(parent_id, []):
                node_copy = node.copy()
                node_copy["subRows"] = build_tree(node["id"])
                tree.append(node_copy)
            return tree

        tree = build_tree()
        cache["assets"] = tree
        return tree

    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")




@router.post("/")
async def create_asset(asset: Dict[str, Any]):
    """
        Create new asset in Google Sheets.

        **Input:**

            - asset (Dict[str, Any]): Asset data in dictionary format
            
        **Process:**

            1. Generate UUID for new asset
            2. Add creation timestamp
            3. Set isDelete flag to 0
            4. Convert asset dict to row format
            5. Append row to Google Sheets
            
        **Output:**

            - Dict: Success message with new asset ID
            - HTTPException: 500 if Google Sheets error occurs
    """
    asset["isDelete"] = 0  # Default to not deleted
    asset["id"] = str(uuid4())
    try:
        sheets = get_google_sheets_service()
        row_to_add = [asset.get(header, "") for header in HEADERS]
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=ASSET_SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": [row_to_add]}
        ).execute()
        cache.clear()  # เพิ่มบรรทัดนี้เพื่อเคลียร์แคช (ใช้ชั่วคราว)
        return asset
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.put("/{asset_id}")
async def update_asset(asset_id: str, updated_data: Dict[str, Any]):
    """
        Update existing asset by ID.

        **Input:**

            - asset_id (str): UUID of asset to update
            - updated_data (Dict[str, Any]): New asset data
            
        **Process:**

            1. Find asset row using binary search
            2. Create update operations for changed fields
            3. Execute batch update in Google Sheets
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if asset not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        # Initialize Google Sheets service
        sheets = get_google_sheets_service()

        # Determine the column index for "id"
        if "id" not in HEADERS:
            raise HTTPException(status_code=500, detail="ID column not defined in headers")
        id_column_index = HEADERS.index("id") + 1  # 1-based index for Google Sheets
        id_column_letter = get_column_letter(id_column_index)  # Convert index to column letter

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
                col_letter = get_column_letter(col_index)
                cell_value = value if isinstance(value, (int, float)) else str(value)
                updates.append({
                    "range": f"{ASSET_SHEET_RANGE}!{col_letter}{row_number}",
                    "values": [[cell_value]]
                })
        
        if updates:
            sheets.values().batchUpdate(
                spreadsheetId=SPREADSHEET_ID, 
                body={"data": updates, "valueInputOption": "RAW"}
            ).execute()
        cache.clear()  # เพิ่มบรรทัดนี้เพื่อเคลียร์แคช (ใช้ชั่วคราว)
        return {"message": "Asset updated successfully"}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    """
        Soft delete asset by setting isDelete flag.

        **Input:**

            - asset_id (str): UUID of asset to delete
            
        **Process:**

            1. Find asset row using binary search
            2. Update isDelete column to 1
            
        **Output:**

            - Dict: Success message
            - HTTPException: 404 if asset not found
            - HTTPException: 500 if Google Sheets error occurs
    """
    try:
        # Initialize Google Sheets service
        sheets = get_google_sheets_service()

        # Determine the column index for "id"
        if "id" not in HEADERS:
            raise HTTPException(status_code=500, detail="ID column not defined in headers")
        id_column_index = HEADERS.index("id") + 1  # 1-based index for Google Sheets
        id_column_letter = get_column_letter(id_column_index)
  # Convert index to column letter

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
            range=f"{ASSET_SHEET_RANGE}!{get_column_letter(col_index)}{row_number}",
            valueInputOption="RAW",
            body={"values": [[1]]}
        ).execute()
        cache.clear()  # เพิ่มบรรทัดนี้เพื่อเคลียร์แคช (ใช้ชั่วคราว)
        return {"message": "Asset marked as deleted"}
    except HttpError as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {e}")

@router.post("/clear-cache")
async def clear_cache():
    """
    Clear the in-memory cache.

    **Process:**
        1. Clear the TTLCache
        2. Return success message

    **Output:**
        - Dict: Success message
    """
    cache.clear()
    return {"message": "Cache cleared successfully"}