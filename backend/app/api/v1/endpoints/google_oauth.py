"""
Google OAuth endpoints for connecting Google Business Profile.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx

from app.core.config import settings
from app.core.deps import get_tenant_id
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.connectors.connector_service import connector_service

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = " ".join([
    "https://www.googleapis.com/auth/business.manage",
    "https://www.googleapis.com/auth/userinfo.email",
])


@router.get("/authorize")
async def google_authorize(
    location_id: uuid.UUID = Query(...),
    tenant_id: uuid.UUID = Query(...),
):
    """Redirect user to Google OAuth consent screen."""
    import urllib.parse
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": f"{tenant_id}:{location_id}",
    }
    query = urllib.parse.urlencode(params)
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback, exchange code for tokens, create connector."""
    try:
        tenant_id_str, location_id_str = state.split(":")
        tenant_id = uuid.UUID(tenant_id_str)
        location_id = uuid.UUID(location_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {response.text}")
        token_data = response.json()

    # Get Google Business accounts
    async with httpx.AsyncClient() as client:
        accounts_response = await client.get(
            "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        accounts_data = accounts_response.json()

    accounts = accounts_data.get("accounts", [])
    if not accounts:
        raise HTTPException(status_code=400, detail=f"No Google Business accounts found. Response: {accounts_data}")

    account_name = accounts[0].get("name", "")

    # Get locations for this account
    async with httpx.AsyncClient() as client:
        locations_response = await client.get(
            f"https://mybusinessbusinessinformation.googleapis.com/v1/{account_name}/locations",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            params={"readMask": "name,title"},
        )
        locations_data = locations_response.json()

    google_locations = locations_data.get("locations", [])
    google_location_id = google_locations[0].get("name", "") if google_locations else account_name

    # Store connector with encrypted credentials
    connector = await connector_service.create_connector(
        db,
        location_id=location_id,
        platform="google_business",
        external_id=google_location_id,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", ""),
        expires_at=token_data.get("expires_in"),
        scope=token_data.get("scope"),
    )

    # Store google-specific fields in credentials
    from app.core.token_vault import retrieve_oauth_tokens, encrypt_token
    creds = retrieve_oauth_tokens(connector.encrypted_credentials)
    creds["account_id"] = account_name
    creds["google_location_id"] = google_location_id
    creds["client_id"] = settings.GOOGLE_CLIENT_ID
    creds["client_secret"] = settings.GOOGLE_CLIENT_SECRET
    connector.encrypted_credentials = encrypt_token(creds)
    await db.commit()

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:40px;background:#f0f9f0">
        <h2 style="color:#1a7a1a">✅ Google Business Connected!</h2>
        <p><b>Account:</b> {account_name}</p>
        <p><b>Location:</b> {google_location_id}</p>
        <p><b>Connector ID:</b> {connector.id}</p>
        <p>You can now trigger a sync from the API to pull your 42 real reviews.</p>
        <p><a href="http://localhost:8000/api/docs">Go to API Docs</a></p>
    </body></html>
    """)

