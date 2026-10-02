"""
One-Time Helper Script: Generate YouTube OAuth2 Refresh Token
Run this script ONCE on your local computer to authorize your YouTube channel
and obtain the REFRESH_TOKEN needed for automated GitHub Actions uploads.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    print("=" * 60)
    print("  YouTube OAuth2 Refresh Token Generator for GitHub Actions")
    print("=" * 60)
    print("\nInstructions:")
    print("1. Go to Google Cloud Console (https://console.cloud.google.com/)")
    print("2. Enable 'YouTube Data API v3'.")
    print("3. Create Credentials -> OAuth 2.0 Client IDs -> Application Type: 'Desktop App'.")
    print("4. Download the JSON file or copy your Client ID and Client Secret.\n")

    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    client_secrets_file = Path("client_secrets.json")

    if client_secrets_file.exists():
        print(f"Found '{client_secrets_file}'. Loading credentials...")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
    else:
        if not client_id:
            client_id = input("Enter your YOUTUBE_CLIENT_ID: ").strip()
        if not client_secret:
            client_secret = input("Enter your YOUTUBE_CLIENT_SECRET: ").strip()

        if not client_id or not client_secret:
            print("Error: Both Client ID and Client Secret are required.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/"]
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nOpening your default browser for authorization...")
    print("Please select your YouTube account and grant upload permissions.\n")

    # Access type offline ensures a refresh token is returned!
    credentials = flow.run_local_server(
        port=8080,
        access_type="offline",
        prompt="consent",
    )

    refresh_token = credentials.refresh_token

    if not refresh_token:
        print("\n[WARNING] No refresh_token was returned.")
        print("This usually happens if consent was already granted without prompt=consent.")
        print("Try removing the app permission in your Google Account security settings and run again.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  AUTHORIZATION SUCCESSFUL! 🎉")
    print("=" * 60)
    print(f"\nYour YOUTUBE_REFRESH_TOKEN:\n\n{refresh_token}\n")

    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=credentials)
        ch_resp = yt.channels().list(part="snippet", mine=True).execute()
        items = ch_resp.get("items", [])
        if items:
            ch_name = items[0]["snippet"]["title"]
            ch_id = items[0]["id"]
            print(f"✅ Verified Connected Channel: '{ch_name}' (ID: {ch_id})")
    except Exception as e:
        print(f"Channel verification note: {e}")

    # Update or create .env file locally
    env_file = Path(".env")
    env_content = ""
    if env_file.exists():
        env_content = env_file.read_text(encoding="utf-8")

    lines = [line for line in env_content.splitlines() if not line.startswith("YOUTUBE_")]
    lines.append(f"YOUTUBE_CLIENT_ID={client_id or 'from_client_secrets'}")
    lines.append(f"YOUTUBE_CLIENT_SECRET={client_secret or 'from_client_secrets'}")
    lines.append(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
    lines.append("YOUTUBE_PRIVACY_STATUS=public")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved credentials to local '{env_file.name}' file.")

    print("\n------------------------------------------------------------")
    print("Next Step for GitHub Actions:")
    print("Go to your GitHub Repo -> Settings -> Secrets and variables -> Actions")
    print("Add the following Repository Secrets:")
    print(f"1. YOUTUBE_CLIENT_ID     : {client_id}")
    print(f"2. YOUTUBE_CLIENT_SECRET : {client_secret}")
    print(f"3. YOUTUBE_REFRESH_TOKEN : {refresh_token}")
    print("------------------------------------------------------------\n")


if __name__ == "__main__":
    main()
