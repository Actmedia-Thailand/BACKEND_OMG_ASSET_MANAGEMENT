from fastapi import FastAPI, HTTPException  # Import FastAPI for building APIs and HTTPException for error handling
from google.oauth2.service_account import Credentials  # For Google Sheets API authentication
from googleapiclient.discovery import build  # For building the Google Sheets API client
from googleapiclient.errors import HttpError  # For handling Google API errors
from typing import List, Dict, Any  # For type hinting
from datetime import datetime, timedelta

# Define the scope for Google Sheets API access
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# Path to the service account credentials file
SERVICE_ACCOUNT_FILE = './credentials.json'

# Initialize the FastAPI application
app = FastAPI()

# Google Sheets configuration: Spreadsheet ID and sheet range to work with
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  # Replace with your Google Sheet ID
SHEET_RANGE = 'Sheet1'  # Replace with the name of the sheet you want to use

# Function to get Google Sheets service
def get_google_sheets_service():
    # Load the service account credentials
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    # Build and return the Google Sheets API service
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

def convert_value(value: str):
    """
    Convert a string value to its appropriate type (int, float, bool, date, or str).
    """
    if value.isdigit():  # Check if the value is an integer
        return int(value)
    try:
        # Attempt to convert to float (handles numbers with decimals)
        return float(value)
    except ValueError:
        # Handle boolean values
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        # Handle date/time strings
        try:
            return datetime.fromisoformat(value)  # ISO 8601 format
        except ValueError:
            # For Google Sheets numeric date format
            try:
                days_since_epoch = float(value)
                return datetime(1899, 12, 30) + timedelta(days=days_since_epoch)
            except ValueError:
                pass
        # Default to returning the string
        return value

# Endpoint to read all items from the Google Sheet
@app.get("/items", response_model=List[Dict[str, Any]])
async def read_items():
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        headers = values[0]  # First row as headers
        # Convert values and build dictionaries
        return [dict(zip(headers, [convert_value(value) for value in row])) for row in values[1:]]
    except HttpError as err:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# Endpoint to add a new item to the Google Sheet
@app.post("/items")
async def create_item(item: Dict[str, Any]):  # Accepts a dictionary as input
    try:
        sheets = get_google_sheets_service()  # Get the Google Sheets service
        # Fetch the current sheet data to validate headers
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE).execute()
        values = result.get('values', [])  # Extract the sheet data
        if not values or not values[0]:  # Ensure the sheet has a header row
            raise HTTPException(status_code=500, detail="Header row is missing in the sheet")

        headers = values[0]  # The first row contains the headers (keys)
        item_keys = set(item.keys())  # Extract the keys from the input JSON
        header_keys = set(headers)  # Convert headers to a set for comparison
        if not item_keys.issubset(header_keys):  # Check if all keys are valid headers
            invalid_keys = item_keys - header_keys  # Identify invalid keys
            raise HTTPException(status_code=400, detail=f"Invalid keys: {', '.join(invalid_keys)}")

        # Create a new row with values ordered to match the headers
        row_to_add = [item.get(header, "") for header in headers]
        # Append the new row to the sheet
        sheets.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE,
            valueInputOption="RAW",  # Write values as raw input
            body={"values": [row_to_add]}  # Wrap the new row in the required body format
        ).execute()
        return {"message": "Item added successfully"}  # Return success message
    except HttpError as err:  # Handle any API errors
        raise HTTPException(status_code=500, detail="Error writing to Google Sheets")

# Endpoint to update an item in the Google Sheet
@app.put("/items/{row}")  # Accepts the row number as a path parameter
async def update_item(row: int, item: Dict[str, str]):  # Takes a dictionary to update the row
    try:
        sheets = get_google_sheets_service()  # Get the Google Sheets service
        # Prepare the values to update
        values = [[value for value in item.values()]]
        # Update the specific row in the sheet
        sheets.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{SHEET_RANGE}!A{row}:Z{row}',  # Update only the specified row
            valueInputOption="RAW",  # Write values as raw input
            body={"values": values}  # Wrap the values in the required body format
        ).execute()
        return {"message": "Item updated successfully"}  # Return success message
    except HttpError as err:  # Handle any API errors
        raise HTTPException(status_code=500, detail="Error updating Google Sheets")

# Endpoint to delete an item from the Google Sheet
@app.delete("/items/{row}")  # Accepts the row number as a path parameter
async def delete_item(row: int):
    try:
        sheets = get_google_sheets_service()  # Get the Google Sheets service
        # Clear the specified row in the sheet
        sheets.values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{SHEET_RANGE}!A{row}:Z{row}'  # Clear the row from columns A to Z
        ).execute()
        return {"message": "Item deleted successfully"}  # Return success message
    except HttpError as err:  # Handle any API errors
        raise HTTPException(status_code=500, detail="Error deleting from Google Sheets")
