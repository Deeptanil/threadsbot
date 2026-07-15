import time
import requests
import asyncio
import os
import json
import logging
import random
from dotenv import load_dotenv, set_key
from fetcher import evaluate_comment_for_reply
from data_log import load_last_posted_time, save_last_posted_time
from text_constants import role_desc

load_dotenv(override=True)
LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation-ender pre-filter — avoids wasting an AI call on dead-end replies
# ---------------------------------------------------------------------------
_CONVERSATION_ENDERS = {
    "lol", "lmao", "haha", "hehe", "ok", "okay", "sure", "nice", "cool", "wow",
    "thanks", "thank you", "ty", "thx", "noted", "agreed", "true", "facts",
    "same", "mood", "fr", "fr fr", "ong", "ngl", "ikr", "yep", "yup", "omg",
    "you too", "u too", "have a great day", "have a good day", "good point",
    "💯", "🔥", "❤️", "🙌", "👏", "😂", "🤣", "👍", "🙏", "😍",
    "💕", "✨", "😭", "🥹", "😊", "🫶", "🪶", "👌",
}

def _is_conversation_ender(text: str) -> bool:
    """Returns True if this comment is a dead-end reply that needs no response."""
    cleaned = text.strip().lower().rstrip("!.,~").strip()
    if len(cleaned) <= 2:
        return True
    return cleaned in _CONVERSATION_ENDERS

async def save_refreshed_token(bot_name, new_token):
    """Saves the refreshed token to the JSON state file for persistence in GitHub Actions."""
    from data_log import save_last_posted_time, load_last_posted_time
    data_log = await load_last_posted_time(bot_name)
    
    await save_last_posted_time(bot_name, data_log.get("last_posted_time", 0), {
        "refreshed_token": new_token
    })
    
    # Also update environment for current run
    if bot_name == "account1" or not bot_name:
        os.environ["THREADS_ACCESS_TOKEN"] = new_token
    else:
        os.environ[f"{bot_name.upper()}_ACCESS_TOKEN"] = new_token
        # Also update the generic one since workflows use it
        os.environ["THREADS_ACCESS_TOKEN"] = new_token
        
    LOG.info(f"Successfully persisted refreshed token for {bot_name} to state file.")
    return True

async def refresh_threads_token(bot_name="account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    if not ACCESS_TOKEN:
        LOG.error(f"No access token found for {bot_name} to refresh.")
        return None

    LOG.info(f"Attempting to refresh token for {bot_name}...")
    refresh_url = "https://graph.threads.net/refresh_access_token"
    params = {
        "grant_type": "th_refresh_token",
        "access_token": ACCESS_TOKEN
    }

    try:
        res = await asyncio.to_thread(requests.get, refresh_url, params=params)
        data = res.json()
        
        if "access_token" in data:
            new_token = data["access_token"]
            await save_refreshed_token(bot_name, new_token)
            return new_token
        else:
            LOG.error(f"Failed to refresh token for {bot_name}: {data}")
            return None
    except Exception as e:
        LOG.error(f"Exception during token refresh for {bot_name}: {e}")
        return None

def get_settings():
    if not os.path.exists("settings.json"):
        return {}
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except:
        return {}

def get_creds(bot_name: str = "account1"):
    # 1. Get account-specific and generic environment values
    prefix = bot_name.upper()
    env_token = os.getenv(f"{prefix}_ACCESS_TOKEN")
    env_user_id = os.getenv(f"{prefix}_USER_ID")
    
    if not env_token:
        env_token = os.getenv("THREADS_ACCESS_TOKEN")
    if not env_user_id:
        env_user_id = os.getenv("THREADS_USER_ID")
        
    # 2. Check for a refreshed token in the JSON state file (highest priority)
    data_file = f"data-{bot_name}.json"
    if os.path.exists(data_file):
        try:
            with open(data_file, "r") as f:
                data = json.load(f)
                if data.get("refreshed_token"):
                    LOG.info(f"Using refreshed token from {data_file}")
                    # Prefer env account-specific ID, then JSON, then fallback env ID
                    uid = env_user_id or data.get("threads_user_id") or os.getenv("THREADS_USER_ID")
                    return data["refreshed_token"], uid
        except:
            pass
            
    return env_token, env_user_id


async def ensure_fresh_token(bot_name="account1"):
    # This could be more sophisticated (checking expiry), but for now 
    # we'll just provide the hook for main.py to call.
    return await refresh_threads_token(bot_name)


async def post_to_threads(text: str, bot_name: str = "account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    
    async def attempt_post(token):
        # Step 1: Create container
        create_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
        create_payload = {
            "media_type": "TEXT",
            "text": text,
            "access_token": token,
        }
        res = await asyncio.to_thread(requests.post, create_url, data=create_payload)
        return res.json()

    data = await attempt_post(ACCESS_TOKEN)

    # Check for OAuth error
    if "error" in data:
        error_msg = data.get("error", {}).get("message", "")
        if "OAuth" in error_msg or data.get("error", {}).get("code") == 190:
            LOG.warning(f"OAuth error detected for {bot_name}. Attempting to refresh token...")
            new_token = await refresh_threads_token(bot_name)
            if new_token:
                LOG.info(f"Token refreshed for {bot_name}, retrying post...")
                data = await attempt_post(new_token)
                ACCESS_TOKEN = new_token # Update for step 2
            else:
                LOG.error(f"Token refresh failed for {bot_name}. Cannot retry.")
                return False, data

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

    # Wait a few seconds for Meta's servers to propagate the container
    await asyncio.sleep(5)

    for attempt in range(3):
        res2 = await asyncio.to_thread(requests.post, publish_url, data=publish_payload)
        res2_json = res2.json()

        if "id" in res2_json:
            LOG.info(f"Post published successfully: {res2_json}")
            return True, res2_json

        error_code = res2_json.get("error", {}).get("code")
        # Code 24 = Media Not Found. This usually means the container isn't ready yet.
        if error_code == 24:
            LOG.warning(f"Media {creation_id} not found yet (attempt {attempt+1}/3). Retrying in 10s...")
            await asyncio.sleep(10)
        else:
            LOG.error(f"Error publishing post (Creation ID: {creation_id}): {res2_json}")
            return False, res2_json

    LOG.error(f"Post publish failed after 3 attempts (Creation ID: {creation_id})")
    return False, res2_json




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
    
    async def attempt_reply(token):
        create_url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
        create_payload = {
            "media_type": "TEXT",
            "text": text,
            "reply_to_id": reply_to_id,
            "access_token": token,
        }
        res = await asyncio.to_thread(requests.post, create_url, data=create_payload)
        return res.json()

    data = await attempt_reply(ACCESS_TOKEN)

    # Check for OAuth error
    if "error" in data:
        error_msg = data.get("error", {}).get("message", "")
        if "OAuth" in error_msg or data.get("error", {}).get("code") == 190:
            LOG.warning(f"OAuth error detected for {bot_name} during reply. Attempting to refresh token...")
            new_token = await refresh_threads_token(bot_name)
            if new_token:
                LOG.info(f"Token refreshed for {bot_name}, retrying reply...")
                data = await attempt_reply(new_token)
                ACCESS_TOKEN = new_token # Update for publish step
            else:
                LOG.error(f"Token refresh failed for {bot_name}. Cannot retry reply.")
                return False, data

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
                await process_replies_recursive(reply_id, bot_name, bot_username, bot_avatar_url, replied_comments, newly_replied, role_desc, new_thread_text, failed_attempts, depth + 1)
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
            elif _is_conversation_ender(text):
                # Fast pre-filter: no AI call needed, conversation is done
                LOG.info(f"Skipping conversation ender from @{username}: '{text}'")
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
                        display_name = os.getenv(f"{bot_name.upper()}_NAME", bot_name)
                        bot_display_username = bot_username or display_name
                        
                        send_discord_embed(
                            title="🚨 Human Review Needed!",
                            description=f"A comment from @{username} was flagged for your review.",
                            fields=[
                                {"name": "User Comment", "value": text, "inline": False},
                                {"name": "Suggested Reply", "value": evaluation.get("suggested_reply", "None"), "inline": False}
                            ],
                            color=0xe74c3c,
                            username=bot_display_username,
                            avatar_url=bot_avatar_url
                        )
                    elif evaluation.get("should_reply") and evaluation.get("reply_text"):
                        reply_text = evaluation["reply_text"]
                        LOG.info(f"Decided to reply with: '{reply_text}'")
                        success, error_data = await reply_to_thread(reply_text, reply_id, bot_name)
                        
                        if success:
                            newly_replied.append(reply_id)
                            failed_attempts.pop(reply_id, None)
                            
                            # Success notification removed to reduce noise.
                            pass
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

async def get_me_data(bot_name="account1"):
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    
    async def attempt_me(token):
        url = f"https://graph.threads.net/v1.0/me?fields=username,threads_profile_picture_url&access_token={token}"
        res = await asyncio.to_thread(requests.get, url)
        return res.json()

    data = await attempt_me(ACCESS_TOKEN)
    
    if "error" in data:
        error_msg = data.get("error", {}).get("message", "")
        if "OAuth" in error_msg or data.get("error", {}).get("code") == 190:
            LOG.warning(f"OAuth error in get_me_data for {bot_name}. Refreshing...")
            new_token = await refresh_threads_token(bot_name)
            if new_token:
                data = await attempt_me(new_token)
            else:
                LOG.error(f"Failed to refresh token for {bot_name} in get_me_data.")
    
    return data

async def handle_auto_replies(role_desc=None, bot_name: str = "account1"):
    LOG.info(f"Checking for new comments to auto-reply for {bot_name}...")
    
    me_data = await get_me_data(bot_name)
    bot_username = me_data.get("username", "")

    data_log = await load_last_posted_time(bot_name)
    threads = await get_recent_threads(bot_name)
    if not threads:
        LOG.info("No recent threads found.")
        return me_data, data_log.get("last_reply_check", time.time())
    replied_comments = data_log.get("replied_comments", [])
    failed_attempts = data_log.get("failed_attempts", {})
    newly_replied = []

    # Check the 20 most recent threads (increased from 10 to catch delayed viral replies)
    for thread in threads[:20]:
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


# ---------------------------------------------------------------------------
# Performance tracking — per-post metrics via Threads Insights API
# ---------------------------------------------------------------------------

async def fetch_post_insights(post_id: str, bot_name: str = "account1") -> dict:
    """Fetch views, likes, replies, reposts for a single post."""
    ACCESS_TOKEN, USER_ID = get_creds(bot_name)
    url = f"https://graph.threads.net/v1.0/{post_id}/insights"
    params = {
        "metric": "views,likes,replies,reposts,quotes",
        "access_token": ACCESS_TOKEN
    }
    try:
        res = await asyncio.to_thread(requests.get, url, params=params)
        data = res.json()
        metrics = {}
        for item in data.get("data", []):
            # Insights returns a list of value objects; grab the first value
            values = item.get("values", [])
            metrics[item["name"]] = values[0].get("value", 0) if values else item.get("total_value", {}).get("value", 0)
        return metrics
    except Exception as e:
        LOG.error(f"Failed to fetch insights for post {post_id}: {e}")
        return {}


async def save_performance_entry(bot_name: str, post_id: str, post_text: str):
    """Record a newly published post in the per-account performance log."""
    filename = f"performance-{bot_name}.json"
    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                perf = json.load(f)
        else:
            perf = {"posts": []}

        perf["posts"].append({
            "id": post_id,
            "text": post_text,
            "posted_at": time.time(),
            "views": None,
            "replies": None,
            "likes": None,
            "reposts": None,
            "last_fetched": None
        })

        # Keep only the last 100 posts to bound file size
        perf["posts"] = perf["posts"][-100:]

        with open(filename, "w") as f:
            json.dump(perf, f, indent=2)
        LOG.info(f"Performance entry saved for post {post_id} ({bot_name})")
    except Exception as e:
        LOG.error(f"Failed to save performance entry: {e}")


async def refresh_performance_log(bot_name: str):
    """
    On each bot run, fetch fresh Threads Insights for any post that:
    - Is less than 7 days old (insights go stale after that)
    - Has not been fetched in the last hour
    """
    filename = f"performance-{bot_name}.json"
    if not os.path.exists(filename):
        return

    try:
        with open(filename, "r") as f:
            perf = json.load(f)
    except Exception:
        return

    now = time.time()
    updated = False

    for entry in perf.get("posts", []):
        last_fetched = entry.get("last_fetched") or 0
        post_age = now - entry.get("posted_at", 0)
        # Only refresh if post is <7 days old and data is >1 hour stale
        if post_age < 7 * 86400 and (now - last_fetched) > 3600:
            metrics = await fetch_post_insights(entry["id"], bot_name)
            if metrics:
                entry["views"]   = metrics.get("views",   entry.get("views"))
                entry["likes"]   = metrics.get("likes",   entry.get("likes"))
                entry["replies"] = metrics.get("replies", entry.get("replies"))
                entry["reposts"] = metrics.get("reposts", entry.get("reposts"))
                entry["last_fetched"] = now
                updated = True
                await asyncio.sleep(0.5)  # gentle rate limiting between insight calls

    if updated:
        with open(filename, "w") as f:
            json.dump(perf, f, indent=2)
        LOG.info(f"Performance log refreshed for {bot_name}")


# ---------------------------------------------------------------------------
# Cross-amplification engine — Solvikz (account1) boosting brand accounts
# ---------------------------------------------------------------------------

async def handle_cross_amplification(solvikz_role: str):
    """
    Occasionally (max once every 3 days) have Solvikz (account1) reply to recent 
    threads of Prettiva (account2) and Strayed (account3) to drive traffic.
    """
    data_log = await load_last_posted_time("account1")
    last_cross = data_log.get("last_cross_reply_time", 0)
    now = time.time()
    
    # 1-day rate limit (86400 seconds)
    if (now - last_cross) < 1 * 24 * 3600:
        LOG.info("Cross-amplification check skipped: rate limit active (last run was recent).")
        return

    # Try Account 2 and Account 3
    targets = ["account2", "account3"]
    # Shuffle targets to avoid prioritizing one over the other
    random.shuffle(targets)
    
    solvikz_username = os.getenv("ACCOUNT1_THREADS_USERNAME", "solvikz")

    for target_acc in targets:
        try:
            threads = await get_recent_threads(target_acc)
            if not threads:
                continue

            # Check the 3 most recent threads
            for thread in threads[:3]:
                thread_id = thread.get("id")
                thread_text = thread.get("text", "")
                if not thread_id or not thread_text:
                    continue

                # Fetch replies to see if we already replied
                replies = await get_thread_replies(thread_id, target_acc)
                already_replied = any(r.get("username") == solvikz_username for r in replies)
                if already_replied:
                    continue

                # Generate a reply from Solvikz's perspective (override_role)
                LOG.info(f"Generating cross-amplification reply for {target_acc} thread: '{thread_text}'")
                eval_res = await evaluate_comment_for_reply(thread_text, override_role=solvikz_role, parent_post_text="")
                if eval_res and eval_res.get("should_reply") and eval_res.get("reply_text"):
                    reply_text = eval_res["reply_text"]
                    LOG.info(f"Posting cross-amplification reply from Solvikz: '{reply_text}'")
                    success, _ = await reply_to_thread(reply_text, thread_id, bot_name="account1")
                    if success:
                        # Save the updated cross reply timestamp
                        await save_last_posted_time("account1", data_log.get("last_posted_time", 0), {
                            "last_cross_reply_time": now
                        })
                        LOG.info(f"Cross-amplification reply successfully posted. Rate limit updated.")
                        return # Only reply to one post per execution run
        except Exception as e:
            LOG.error(f"Error checking cross-amplification for {target_acc}: {e}")