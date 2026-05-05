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


import logging
from fetcher import evaluate_comment_for_reply
from data_log import load_last_posted_time, save_last_posted_time

LOG = logging.getLogger(__name__)

async def get_recent_threads():
    url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
    params = {
        "fields": "id,text",
        "access_token": ACCESS_TOKEN
    }
    res = await asyncio.to_thread(requests.get, url, params=params)
    data = res.json()
    if "data" in data:
        return data["data"]
    return []

async def get_thread_replies(media_id):
    url = f"https://graph.threads.net/v1.0/{media_id}/replies"
    params = {
        "fields": "id,text,username,has_replies",
        "access_token": ACCESS_TOKEN
    }
    res = await asyncio.to_thread(requests.get, url, params=params)
    data = res.json()
    if "data" in data:
        return data["data"]
    return []

async def reply_to_thread(text: str, reply_to_id: str):
    create_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
    create_payload = {
        "media_type": "TEXT",
        "text": text,
        "reply_to_id": reply_to_id,
        "access_token": ACCESS_TOKEN,
    }
    res = await asyncio.to_thread(requests.post, create_url, data=create_payload)
    data = res.json()

    if "id" not in data:
        LOG.error(f"Error creating reply: {data}")
        return False

    creation_id = data["id"]
    publish_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    }
    res2 = await asyncio.to_thread(requests.post, publish_url, data=publish_payload)
    res2_json = res2.json()
    if "error" in res2_json:
        LOG.error(f"Reply publish failed: {res2_json}")
        return False
        
    LOG.info(f"Reply published: {res2_json}")
    return True

async def process_replies_recursive(media_id, bot_username, replied_comments, newly_replied, role_desc, thread_text, failed_attempts, depth=1):
    if depth > 6:
        return
        
    replies = await get_thread_replies(media_id)
    for reply in replies:
        reply_id = reply.get("id")
        text = reply.get("text", "")
        username = reply.get("username", "")
        has_replies = reply.get("has_replies", False)

        # 1. Process this specific comment
        if reply_id in replied_comments or reply_id in newly_replied:
            pass # Already processed
        elif username == bot_username:
            pass # Don't process our own comments
        else:
            # Check if we manually replied to this specific comment
            already_replied_by_us = False
            if has_replies:
                sub_replies = await get_thread_replies(reply_id)
                for sub in sub_replies:
                    if sub.get("username") == bot_username:
                        already_replied_by_us = True
                        break
            
            if already_replied_by_us:
                LOG.info(f"Skipping comment from @{username} because we already replied to it.")
                newly_replied.append(reply_id)
            else:
                LOG.info(f"Evaluating new comment from @{username}: '{text}'")
                evaluation = await evaluate_comment_for_reply(text, role_desc, parent_post_text=thread_text)

                if evaluation is None:
                    # Strike system for failures
                    strikes = failed_attempts.get(reply_id, 0) + 1
                    failed_attempts[reply_id] = strikes
                    if strikes >= 3:
                        LOG.warning(f"Comment {reply_id} failed evaluation 3 times. Adding to ignore pile.")
                        newly_replied.append(reply_id)
                        failed_attempts.pop(reply_id, None)
                    else:
                        LOG.warning(f"Comment {reply_id} failed evaluation. Strike {strikes}/3. Will retry next time.")
                else:
                    if evaluation.get("should_reply") and evaluation.get("reply_text"):
                        reply_text = evaluation["reply_text"]
                        LOG.info(f"Decided to reply with: '{reply_text}'")
                        success = await reply_to_thread(reply_text, reply_id)
                        newly_replied.append(reply_id)
                        
                        if success:
                            from discord_notifier import send_discord_notification
                            send_discord_notification(f"💬 **New Auto-Reply!**\n**Context:** {thread_text}\n**User (@{username}):** {text}\n**Bot:** {reply_text}")
                    else:
                        LOG.info("Decided to ignore this comment.")
                        newly_replied.append(reply_id)
                    
                    failed_attempts.pop(reply_id, None)
                
                await asyncio.sleep(2)

        # 2. Recursively process its children to catch fans replying back to us!
        if has_replies:
            new_thread_text = f"{thread_text}\n[Reply by @{username}]: {text}"
            await process_replies_recursive(reply_id, bot_username, replied_comments, newly_replied, role_desc, new_thread_text, failed_attempts, depth + 1)

async def handle_auto_replies(role_desc=None):
    LOG.info("Checking for new comments to auto-reply...")
    
    me_url = f"https://graph.threads.net/v1.0/me?fields=username&access_token={ACCESS_TOKEN}"
    me_res = await asyncio.to_thread(requests.get, me_url)
    me_data = me_res.json()
    bot_username = me_data.get("username", "")

    threads = await get_recent_threads()
    if not threads:
        LOG.info("No recent threads found.")
        return

    data_log = await load_last_posted_time()
    replied_comments = data_log.get("replied_comments", [])
    failed_attempts = data_log.get("failed_attempts", {})
    newly_replied = []

    # Check the 10 most recent threads
    for thread in threads[:10]:
        thread_id = thread.get("id")
        thread_text = thread.get("text", "")
        await process_replies_recursive(thread_id, bot_username, replied_comments, newly_replied, role_desc, thread_text, failed_attempts)

    if newly_replied or failed_attempts != data_log.get("failed_attempts", {}):
        replied_comments.extend(newly_replied)
        if len(replied_comments) > 2000:
            replied_comments = replied_comments[-2000:]
        
        # Clean up failed_attempts for extremely old ones to save memory
        if len(failed_attempts) > 1000:
            failed_attempts = {}
            
        await save_last_posted_time(data_log.get("last_posted_time", 0), {
            "replied_comments": replied_comments,
            "failed_attempts": failed_attempts
        })
        
    LOG.info("Finished auto-reply check.")