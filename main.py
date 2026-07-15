import asyncio
import logging
import random
import sys
import time
import os
from pathlib import Path

import click
from dotenv import load_dotenv

from api import post_to_threads, get_settings
from data_log import load_last_posted_time, save_last_posted_time
from fetcher import posts_exist, generate_posts_batch, save_batch, get_next_post
from logging_setup import setup_logging

MINIMUM_TIMESPAN_BETWEEN_POSTS = 60 * 60 * 2
LOG = logging.getLogger(__name__)
load_dotenv(override=True)

# IST = UTC+5:30 = 19800 seconds ahead of UTC
_IST_OFFSET_SECS = 19800

def adjust_for_dead_hours(timestamp: float) -> float:
    """
    Ensures a scheduled post does not fall in the dead zone (1 AM–7 AM IST).
    If it does, the timestamp is pushed forward to 7 AM IST of the same day.
    """
    ist_day_secs = (int(timestamp) + _IST_OFFSET_SECS) % 86400  # seconds past midnight IST
    dead_start = 1 * 3600   # 01:00 IST
    dead_end   = 7 * 3600   # 07:00 IST
    if dead_start <= ist_day_secs < dead_end:
        seconds_until_clear = dead_end - ist_day_secs
        LOG.info(f"Post falls in dead zone (1–7 AM IST). Pushing forward by {seconds_until_clear // 60:.0f} minutes.")
        return timestamp + seconds_until_clear
    return timestamp


@click.command()
@click.argument("bot_name")
@click.option("-r", "--role-txt-path", required=False, default=None)
@click.option("-c", "--creds-file-path", required=False, default=None)
@click.option("-f", "--post-frequency", required=False, default=MINIMUM_TIMESPAN_BETWEEN_POSTS,
              help="Post frequency in seconds")
def main_func(bot_name: str, role_txt_path: str, creds_file_path: str = None, post_frequency=None) -> None:
    if role_txt_path:
        try:
            with open(role_txt_path, "r") as file:
                role_desc = file.read()
        except FileNotFoundError:
            click.echo(f"Error: File '{role_txt_path}' not found.")
            return
        except Exception as e:
            click.echo(f"Error reading file '{role_txt_path}': {e}")
            return
    else:
        role_desc = None

    if creds_file_path:
        if not Path(creds_file_path).is_file():
            click.echo(f"Error: File '{creds_file_path}' not found.")
            return

    asyncio.run(main(bot_name, role_desc, creds_file_path, post_frequency))


async def main(bot_name: str, role_desc: str = None, creds_file: str = None,
               post_frequency=None) -> None:
    
    # 0. Ensure tokens are fresh
    from api import ensure_fresh_token, refresh_performance_log
    try:
        await ensure_fresh_token(bot_name)
    except Exception as e:
        LOG.warning(f"Could not refresh token for {bot_name}: {e}")

    # 0b. Refresh performance metrics for recent posts (non-blocking)
    try:
        await refresh_performance_log(bot_name)
    except Exception as e:
        LOG.warning(f"Performance log refresh skipped: {e}")

    # 1. ALWAYS run the auto-reply engine every time the script wakes up
    from api import handle_auto_replies
    try:
        me_data, last_check_time = await handle_auto_replies(role_desc, bot_name)
    except Exception as e:
        LOG.error(f"Error during auto-reply check: {e}")
        me_data, last_check_time = {}, time.time()

    # 1b. Run cross-amplification engine if we are Account 1 (Solvikz)
    if bot_name == "account1":
        from api import handle_cross_amplification
        try:
            sol_role = role_desc
            if not sol_role:
                try:
                    with open("roles/account1.txt", "r") as f:
                        sol_role = f.read()
                except Exception:
                    sol_role = None
            if sol_role:
                await handle_cross_amplification(sol_role)
        except Exception as e:
            LOG.error(f"Error during cross-amplification check: {e}")
        
    current_time = time.time()
    last_posted_time = await load_last_posted_time(bot_name)
    next_post_time = last_posted_time.get("next_post_time", 0)
    
    if current_time < next_post_time:
        minutes_left = (next_post_time - current_time) / 60
        LOG.info(f"Not time to post yet. Waiting approx {minutes_left:.1f} more minutes. Exiting...")
        sys.exit(0)

    from fetcher import peek_next_post, remove_post
    
    if not await posts_exist(bot_name):
        LOG.info("Generating a new batch of posts...")
        data_log = await load_last_posted_time(bot_name)
        last_had_promo = data_log.get("last_posted_was_promo", False)
        batch = await generate_posts_batch("Make a batch", role_desc, last_had_promo=last_had_promo, bot_name=bot_name)
        await save_batch(bot_name, batch)

    post_data = await peek_next_post(bot_name)
    if post_data is None:
        LOG.info("Generating a new batch of posts...")
        data_log = await load_last_posted_time(bot_name)
        last_had_promo = data_log.get("last_posted_was_promo", False)
        batch = await generate_posts_batch("Make a batch", role_desc, last_had_promo=last_had_promo, bot_name=bot_name)
        await save_batch(bot_name, batch)
        post_data = await peek_next_post(bot_name)
    
    if post_data is None:
        LOG.error(f"Failed to get or generate posts for {bot_name}.")
        return

    post_text, reach, is_promo = post_data
    
    settings = get_settings().get(bot_name, {})
    approval_mode = settings.get("approval_mode", False)
    min_gap = float(settings.get("min_gap_hours", 2))
    max_gap = float(settings.get("max_gap_hours", 3.5))

    posts_made = last_posted_time.get("post_count", 0)
    
    # Calculate a random delay based on settings, then guard against the dead zone
    random_delay = random.randint(int(min_gap * 3600), int(max_gap * 3600))
    new_next_post_time = adjust_for_dead_hours(current_time + random_delay)
    
    from discord_notifier import send_discord_embed

    if approval_mode:
        LOG.info(f"Approval Mode is ON. Moving post to pending for {bot_name}.")
        import json
        pending = []
        if os.path.exists(f"pending-{bot_name}.json"):
            with open(f"pending-{bot_name}.json", "r") as f:
                pending = json.load(f)
        pending.append(post_text)
        with open(f"pending-{bot_name}.json", "w") as f:
            json.dump(pending, f)
        
        # Remove from candidate list
        await remove_post(bot_name, post_text)
        
        await save_last_posted_time(bot_name, current_time, {
            "post_count": posts_made, 
            "next_post_time": new_next_post_time,
            "last_posted_was_promo": is_promo
        })
        
        # Get display name for notification
        display_name = os.getenv(f"{bot_name.upper()}_NAME", bot_name)
        bot_username = me_data.get("username") or display_name

        send_discord_embed(
            title="⏳ Post Pending Approval",
            description=f"> {post_text}\n\nApprove this post from the Command Center Dashboard.",
            color=0xf39c12,
            username=bot_username,
            avatar_url=me_data.get("threads_profile_picture_url")
        )
    else:
        LOG.info(f"Posting to Threads: {post_text}")
        success, error_data = await post_to_threads(post_text, bot_name)
        
        if success:
            # Remove from candidate list ONLY on success
            await remove_post(bot_name, post_text)
            
            posts_made += 1
            
            await save_last_posted_time(bot_name, current_time, {
                "post_count": posts_made, 
                "next_post_time": new_next_post_time,
                "last_posted_was_promo": is_promo
            })
            
            LOG.info(f"Post made successfully. Total posts: {posts_made}.")
            LOG.info(f"Next post will be around {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_next_post_time))}. Exiting.")

            # Record this post in the performance log for metric tracking
            post_id = error_data.get("id")
            if post_id:
                from api import save_performance_entry
                try:
                    await save_performance_entry(bot_name, post_id, post_text)
                except Exception as e:
                    LOG.warning(f"Could not save performance entry: {e}")

            # Send Success to Discord
            # Get display name for notification
            display_name = os.getenv(f"{bot_name.upper()}_NAME", bot_name)
            bot_username = me_data.get("username") or display_name

            # Success notification removed to reduce noise as per user request.
            # Only errors and approval requests will be sent to Discord.
        else:
            LOG.error(f"Post failed for {bot_name}: {error_data}")
            # We do NOT update next_post_time. It stays in the past.
            # We do NOT remove the post from the candidate list.
            LOG.info(f"Post failed. Timer remains at its previous value. Will retry in the next run.")

            # Send Error to Discord
            display_name = os.getenv(f"{bot_name.upper()}_NAME", bot_name)
            bot_username = me_data.get("username") or display_name
            error_msg = error_data.get("error", {}).get("message", "Unknown error")
            send_discord_embed(
                title="⚠️ Threads Posting Failed",
                description=f"Bot attempted to post but encountered an error.\n\n**Error:** {error_msg}\n\n*Note: The bot will retry this post automatically in the next run.*",
                fields=[
                    {"name": "Bot Account", "value": display_name, "inline": True},
                    {"name": "Internal ID", "value": bot_name, "inline": True},
                    {"name": "Post Content", "value": post_text[:200] + "..." if len(post_text) > 200 else post_text, "inline": False}
                ],
                color=0xe74c3c,
                username=bot_username,
                avatar_url=me_data.get("threads_profile_picture_url")
            )



if __name__ == "__main__":
    setup_logging()
    LOG.info("Starting bot run...")
    main_func()
