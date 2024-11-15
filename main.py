from fastapi import FastAPI, HTTPException
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict

# ติดตั้ง Google Sheets API credentials
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = './credentials.json'  # แทนที่ด้วย path ที่ถูกต้องของไฟล์ credentials.json

# สร้าง FastAPI app
app = FastAPI()

# สร้างการเชื่อมต่อกับ Google Sheets
def get_google_sheets_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

# การตั้งค่า Google Sheets ID และ Range ที่ใช้ในการทำ CRUD
SPREADSHEET_ID = '1OaMBaxjFFlzZrIEkTA8dGdVeCZ_UaaWGc9EKbVpvkcM'  # แทนที่ด้วย ID ของ Google Sheet ของคุณ
SHEET_RANGE = 'Sheet1'  # แทนที่ด้วยชื่อ sheet และ range ที่ต้องการใช้งาน

# อ่านข้อมูลจาก Google Sheets
@app.get("/items", response_model=List[Dict[str, str]])#Specifies that the response model will be a List of Dict with string keys and values.
async def read_items():
    try:
        sheets = get_google_sheets_service()
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE).execute()
        values = result.get('values', [])
        if not values:
            raise HTTPException(status_code=404, detail="No data found")
        return [dict(zip(values[0], row)) for row in values[1:]]
    except HttpError as err:
        raise HTTPException(status_code=500, detail="Error reading from Google Sheets")

# เพิ่มข้อมูลใน Google Sheets
@app.post("/items")
async def create_item(item: Dict[str, str]):
    try:
        sheets = get_google_sheets_service()
        values = [[value for value in item.values()]]
        sheets.values().append(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE, valueInputOption="RAW", body={"values": values}).execute()
        return {"message": "Item added successfully"}
    except HttpError as err:
        raise HTTPException(status_code=500, detail="Error writing to Google Sheets")

# อัพเดทข้อมูลใน Google Sheets
@app.put("/items/{row}")
async def update_item(row: int, item: Dict[str, str]):
    try:
        sheets = get_google_sheets_service()
        values = [[value for value in item.values()]]
        sheets.values().update(spreadsheetId=SPREADSHEET_ID, range=f'{SHEET_RANGE}!A{row}:Z{row}', valueInputOption="RAW", body={"values": values}).execute()
        return {"message": "Item updated successfully"}
    except HttpError as err:
        raise HTTPException(status_code=500, detail="Error updating Google Sheets")

# ลบข้อมูลจาก Google Sheets
@app.delete("/items/{row}")
async def delete_item(row: int):
    try:
        sheets = get_google_sheets_service()
        sheets.values().clear(spreadsheetId=SPREADSHEET_ID, range=f'{SHEET_RANGE}!A{row}:Z{row}').execute()
        return {"message": "Item deleted successfully"}
    except HttpError as err:
        raise HTTPException(status_code=500, detail="Error deleting from Google Sheets")
