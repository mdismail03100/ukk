import logging
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from src.config import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    YOUTUBE_PRIVACY_STATUS,
    VIDEO_TITLE_PREFIX,
    VIDEO_TAGS,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_authenticated_service(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
):
    """
    Builds an authenticated YouTube Data API v3 service client headlessly
    using OAuth2 Refresh Token (ideal for GitHub Actions CI/CD and local automated runs).
    """
    # Reload local .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    c_id = client_id or os.getenv("YOUTUBE_CLIENT_ID", YOUTUBE_CLIENT_ID)
    c_sec = client_secret or os.getenv("YOUTUBE_CLIENT_SECRET", YOUTUBE_CLIENT_SECRET)
    r_tok = refresh_token or os.getenv("YOUTUBE_REFRESH_TOKEN", YOUTUBE_REFRESH_TOKEN)

    if not (c_id and c_sec and r_tok):
        raise ValueError(
            "YouTube credentials are not configured! Please configure YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN in your .env file or run "
            "'python scripts/generate_token.py' to authenticate."
        )

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=r_tok,
        token_uri=TOKEN_URI,
        client_id=c_id,
        client_secret=c_sec,
        scopes=YOUTUBE_UPLOAD_SCOPE,
    )

    logger.info("Refreshing YouTube OAuth2 access token...")
    credentials.refresh(Request())
    logger.info("Successfully authenticated with YouTube Data API v3.")

    return build("youtube", "v3", credentials=credentials)


def check_youtube_auth() -> Dict[str, any]:
    """
    Checks if YouTube API credentials are valid and returns channel details.
    """
    try:
        youtube = get_authenticated_service()
        # Retrieve authenticated channel details
        request = youtube.channels().list(
            part="snippet,statistics",
            mine=True
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            channel = items[0]
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})
            return {
                "authenticated": True,
                "channel_id": channel.get("id"),
                "channel_title": snippet.get("title", "My YouTube Channel"),
                "custom_url": snippet.get("customUrl", ""),
                "subscriber_count": stats.get("subscriberCount", "Hidden"),
                "video_count": stats.get("videoCount", "0"),
                "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            }
        return {
            "authenticated": True,
            "channel_title": "Authenticated Channel",
            "channel_id": "",
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e)
        }


def upload_youtube_short(
    video_path: Path,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacy_status: str = YOUTUBE_PRIVACY_STATUS,
) -> Dict[str, str]:
    """
    Uploads a video to YouTube with Shorts formatting and tags.
    """
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file to upload not found: {video_path}")

    # Build title with mandatory #Shorts hashtag
    if not title:
        titles = [
            f"{VIDEO_TITLE_PREFIX} | Wait For It #Shorts",
            f"Pure Adrenaline Scene 🔥 #Shorts #Phonk",
            f"When The Beat Drops Hard ⚡ #Shorts #Action",
            f"Most Badass Action Moment 💀 #Shorts",
        ]
        title = random.choice(titles)
    elif "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"

    # Description and hashtags
    if not description:
        description = (
            f"{title}\n\n"
            "Cinematic action synced with high-energy beats.\n"
            "Like and Subscribe for daily action edits!\n\n"
            "#Shorts #YouTubeShorts #Action #Phonk #Cinematic #Badass #Viral #FYP"
        )

    if tags is None:
        tags = VIDEO_TAGS

    body = {
        "snippet": {
            "title": title[:100],  # YouTube title limit is 100 chars
            "description": description[:5000],
            "tags": tags,
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    youtube = get_authenticated_service()

    # Resumable upload chunking (8MB per chunk)
    media = MediaFileUpload(
        str(video_path),
        chunksize=1024 * 1024 * 8,
        resumable=True,
        mimetype="video/mp4",
    )

    logger.info(f"Starting upload for '{video_path.name}' to YouTube as '{privacy_status}'...")
    logger.info(f"Title: {title}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry_count = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload Progress: {progress}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry_count += 1
                if retry_count > max_retries:
                    raise
                sleep_time = random.uniform(2, 10) * (2 ** retry_count)
                logger.warning(f"Network error ({e.resp.status}). Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                raise

    video_id = response.get("id")
    shorts_url = f"https://www.youtube.com/shorts/{video_id}"
    logger.info(f"Video uploaded successfully! Video ID: {video_id}")
    logger.info(f"Watch Short here: {shorts_url}")

    return {
        "id": video_id,
        "url": shorts_url,
        "title": title,
    }
