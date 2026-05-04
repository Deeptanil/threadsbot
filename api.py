import requests
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
USER_ID = os.getenv("THREADS_USER_ID")


async def post_to_threads(text: str, creds_file=None):
    # Step 1: Create container
    create_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"

    create_payload = {
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }

    res = await asyncio.to_thread(requests.post, create_url, data=create_payload)
    data = res.json()

    if "id" not in data:
        print("Error creating post:", data)
        return

    creation_id = data["id"]

    # Step 2: Publish post
    publish_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish"

    publish_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    }

    res2 = await asyncio.to_thread(requests.post, publish_url, data=publish_payload)
    print("Response:", res2.json())