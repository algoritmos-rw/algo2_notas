"""Cliente de Google Sheets compartido por update_entregas y check_deadlines."""

import gspread
from google.oauth2.service_account import Credentials

import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def open_spreadsheet():
    creds = Credentials.from_service_account_file(
        config.SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client.open_by_key(config.SPREADSHEET_KEY)
