import time
import requests
import asyncio
import os
from dotenv import load_dotenv

import json

def get_settings():
    if not os.path.exists("settings.json"):
        return {}
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except:
        return {}

def get_creds(bot_name: str = "account1"):
    if not bot_name or bot_name == "account1":
        return os.getenv("THREADS_ACCESS_TOKEN"), os.getenv("THREADS_USER_ID")
    prefix = bot_name.upper()
    return os.getenv(f"{prefix}_ACCESS_TOKEN"), os.getenv(f"{prefix}_USER_ID")


async def post_to_threads(text: str, bot_name: str = "account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
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
        LOG.error(f"Error creating post container: {data}")
        return False, data

    creation_id = data["id"]

    # Step 2: Publish post
    publish_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish"

    publish_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    }

    res2 = await asyncio.to_thread(requests.post, publish_url, data=publish_payload)
    res2_json = res2.json()
    
    if "id" in res2_json:
        LOG.info(f"Post published successfully: {res2_json}")
        return True, res2_json
    else:
        LOG.error(f"Error publishing post: {res2_json}")
        return False, res2_json


import logging
from fetcher import evaluate_comment_for_reply
from data_log import load_last_posted_time, save_last_posted_time

LOG = logging.getLogger(__name__)

async def get_recent_threads(bot_name="account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
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

async def get_thread_replies(media_id, bot_name="account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
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

async def reply_to_thread(text: str, reply_to_id: str, bot_name="account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    LOG.info(f"Attempting to reply to ID: {reply_to_id}")
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
        LOG.error(f"Error creating reply container for {reply_to_id}: {data}")
        return False, data

    creation_id = data["id"]
    publish_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    }
    
    # Wait a few seconds for Meta's servers to propagate the container
    await asyncio.sleep(5)
    
    for attempt in range(3):
        res2 = await asyncio.to_thread(requests.post, publish_url, data=publish_payload)
        res2_json = res2.json()
        
        if "id" in res2_json:
            LOG.info(f"Reply published successfully: {res2_json}")
            return True, res2_json
            
        error_code = res2_json.get("error", {}).get("code")
        # Code 24 = Media Not Found. This usually means the container isn't ready yet.
        if error_code == 24:
            LOG.warning(f"Media {creation_id} not found yet (attempt {attempt+1}/3). Retrying in 10s...")
            await asyncio.sleep(10)
        else:
            LOG.error(f"Reply publish failed for {reply_to_id} (Creation ID: {creation_id}): {res2_json}")
            return False, res2_json
            
    LOG.error(f"Reply publish failed after 3 attempts for {reply_to_id}")
    return False, res2_json

async def process_replies_recursive(media_id, bot_name, bot_username, bot_avatar_url, replied_comments, newly_replied, role_desc, thread_text, failed_attempts, depth=1):
    if depth > 6:
        return
        
    replies = await get_thread_replies(media_id, bot_name)
    for reply in replies:
        reply_id = reply.get("id")
        text = reply.get("text", "")
        username = reply.get("username", "")
        has_replies = reply.get("has_replies", False)

        # 1. Skip if already processed, if it's us, or if user is blocklisted
        settings = get_settings()
        blocklist = settings.get("global", {}).get("blocklist", [])
        
        if username in blocklist:
            LOG.info(f"Skipping comment from @{username} because they are on the blocklist.")
            newly_replied.append(reply_id)
            continue
            
        if reply_id in replied_comments or reply_id in newly_replied:
            pass
        elif username == bot_username:
            # We don't reply to ourselves, but we ALWAYS recurse into our own replies 
            # to see if fans replied back to us!
            if has_replies:
                new_thread_text = f"{thread_text}\n[Reply by @{username}]: {text}"
                await process_replies_recursive(reply_id, bot_username, replied_comments, newly_replied, role_desc, new_thread_text, failed_attempts, depth + 1)
            continue
        else:
            # 2. Check if we already replied (more efficiently)
            already_replied_by_us = False
            sub_replies = []
            if has_replies:
                sub_replies = await get_thread_replies(reply_id, bot_name)
                for sub in sub_replies:
                    if sub.get("username") == bot_username:
                        already_replied_by_us = True
                        break
            
            if already_replied_by_us:
                LOG.info(f"Skipping comment from @{username} because we already replied to it.")
                newly_replied.append(reply_id)
            elif not text or text.strip() == "":
                LOG.info(f"Skipping comment from @{username} because it has no text (Sticker/GIF).")
                newly_replied.append(reply_id)
            else:
                # 3. Evaluate and Reply
                LOG.info(f"Evaluating new comment from @{username}: '{text}'")
                evaluation = await evaluate_comment_for_reply(text, role_desc, parent_post_text=thread_text)

                if evaluation is None:
                    strikes = failed_attempts.get(reply_id, 0) + 1
                    failed_attempts[reply_id] = strikes
                    if strikes >= 3:
                        LOG.warning(f"Comment {reply_id} failed evaluation 3 times. Skipping.")
                        newly_replied.append(reply_id)
                        failed_attempts.pop(reply_id, None)
                else:
                    if evaluation.get("needs_review"):
                        LOG.warning(f"Comment from @{username} flagged for human review.")
                        from fetcher import save_json, load_json
                        review_queue = []
                        if os.path.exists(f"review-{bot_name}.json"):
                            with open(f"review-{bot_name}.json", "r") as f:
                                review_queue = json.load(f)
                        
                        review_queue.append({
                            "reply_id": reply_id,
                            "username": username,
                            "text": text,
                            "suggested_reply": evaluation.get("suggested_reply", ""),
                            "parent_thread": thread_text
                        })
                        with open(f"review-{bot_name}.json", "w") as f:
                            json.dump(review_queue, f)
                            
                        newly_replied.append(reply_id)
                        failed_attempts.pop(reply_id, None)
                        
                        from discord_notifier import send_discord_embed
                        send_discord_embed(
                            title="🚨 Human Review Needed!",
                            description=f"A comment from @{username} was flagged for your review.",
                            fields=[
                                {"name": "User Comment", "value": text, "inline": False},
                                {"name": "Suggested Reply", "value": evaluation.get("suggested_reply", "None"), "inline": False}
                            ],
                            color=0xe74c3c,
                            username=bot_username,
                            avatar_url=bot_avatar_url
                        )
                    elif evaluation.get("should_reply") and evaluation.get("reply_text"):
                        reply_text = evaluation["reply_text"]
                        LOG.info(f"Decided to reply with: '{reply_text}'")
                        success, error_data = await reply_to_thread(reply_text, reply_id, bot_name)
                        
                        if success:
                            newly_replied.append(reply_id)
                            failed_attempts.pop(reply_id, None)
                            
                            from discord_notifier import send_discord_embed
                            original_thread = thread_text.split('\n[Reply by')[0]
                            if len(original_thread) > 1000:
                                original_thread = original_thread[:1000] + "..."
                                
                            fields = [
                                {"name": "Original Thread", "value": original_thread, "inline": False},
                                {"name": f"User Comment (@{username})", "value": text, "inline": False},
                                {"name": "Bot Reply", "value": reply_text, "inline": False}
                            ]
                            send_discord_embed(
                                title="💬 Auto-Reply Triggered",
                                fields=fields,
                                color=0x2ecc71,
                                username=bot_username,
                                avatar_url=bot_avatar_url
                            )
                        else:
                            # Handle specific errors
                            error_code = error_data.get("error", {}).get("code")
                            if error_code == 24: # Media Not Found
                                LOG.warning(f"Media {reply_id} not found. Adding to ignore pile.")
                                newly_replied.append(reply_id)
                                failed_attempts.pop(reply_id, None)
                            else:
                                # Other errors (transient)
                                strikes = failed_attempts.get(reply_id, 0) + 1
                                failed_attempts[reply_id] = strikes
                                if strikes >= 3:
                                    newly_replied.append(reply_id)
                                    failed_attempts.pop(reply_id, None)
                    else:
                        LOG.info("Decided to ignore this comment.")
                        newly_replied.append(reply_id)
                        failed_attempts.pop(reply_id, None)
                
                await asyncio.sleep(2)

            # 4. Recurse into this comment (if it has replies that aren't from us yet)
            if has_replies and not already_replied_by_us:
                new_thread_text = f"{thread_text}\n[Reply by @{username}]: {text}"
                await process_replies_recursive(reply_id, bot_name, bot_username, bot_avatar_url, replied_comments, newly_replied, role_desc, new_thread_text, failed_attempts, depth + 1)

async def handle_auto_replies(role_desc=None, bot_name: str = "account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    LOG.info(f"Checking for new comments to auto-reply for {bot_name}...")
    
    me_url = f"https://graph.threads.net/v1.0/me?fields=username,threads_profile_picture_url&access_token={ACCESS_TOKEN}"
    me_res = await asyncio.to_thread(requests.get, me_url)
    me_data = me_res.json()
    bot_username = me_data.get("username", "")

    data_log = await load_last_posted_time(bot_name)
    threads = await get_recent_threads(bot_name)
    if not threads:
        LOG.info("No recent threads found.")
        return me_data, data_log.get("last_reply_check", time.time())
    replied_comments = data_log.get("replied_comments", [])
    failed_attempts = data_log.get("failed_attempts", {})
    newly_replied = []

    # Check the 10 most recent threads
    for thread in threads[:10]:
        thread_id = thread.get("id")
        thread_text = thread.get("text", "")
        await process_replies_recursive(thread_id, bot_name, bot_username, me_data.get("threads_profile_picture_url"), replied_comments, newly_replied, role_desc, thread_text, failed_attempts)

    if newly_replied or failed_attempts != data_log.get("failed_attempts", {}):
        replied_comments.extend(newly_replied)
        if len(replied_comments) > 2000:
            replied_comments = replied_comments[-2000:]
        
        # Clean up failed_attempts for extremely old ones to save memory
        if len(failed_attempts) > 1000:
            failed_attempts = {}
            
    await save_last_posted_time(bot_name, data_log.get("last_posted_time", 0), {
        "replied_comments": replied_comments,
        "failed_attempts": failed_attempts,
        "last_reply_check": time.time()
    })
        
    LOG.info(f"Finished auto-reply check for {bot_name}.")
    return me_data, data_log.get("last_reply_check", time.time())