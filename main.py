import asyncio
import logging
import random
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv

from api import post_to_threads
from data_log import load_last_posted_time, save_last_posted_time
from fetcher import posts_exist, generate_posts_batch, save_batch, get_next_post
from logging_setup import setup_logging

MINIMUM_TIMESPAN_BETWEEN_POSTS = 60 * 60 * 2
LOG = logging.getLogger(__name__)
load_dotenv()


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
    
    # 1. ALWAYS run the auto-reply engine every time the script wakes up
    from api import handle_auto_replies
    try:
        await handle_auto_replies(role_desc, bot_name)
    except Exception as e:
        LOG.error(f"Error during auto-reply check: {e}")
        
    current_time = time.time()
    last_posted_time = await load_last_posted_time(bot_name)
    next_post_time = last_posted_time.get("next_post_time", 0)
    
    if current_time < next_post_time:
        minutes_left = (next_post_time - current_time) / 60
        LOG.info(f"Not time to post yet. Waiting approx {minutes_left:.1f} more minutes. Exiting...")
        sys.exit(0)

    if not await posts_exist(bot_name):
        LOG.info("Generating a new batch of posts...")
        batch = await generate_posts_batch("Make a batch", role_desc)
        await save_batch(bot_name, batch)

    post = await get_next_post(bot_name)
    if post is None:
        LOG.info("Generating a new batch of posts...")
        batch = await generate_posts_batch("Make a batch", role_desc)
        await save_batch(bot_name, batch)
        post = await get_next_post(bot_name)
    
    LOG.info(f"Posting to Threads: {post[0]}")
    await post_to_threads(post[0], creds_file)
    
    posts_made = last_posted_time.get("post_count", 0) + 1
    
    # Calculate a random delay between 2 hours and 3.5 hours
    random_delay = random.randint(2 * 3600, int(3.5 * 3600))
    new_next_post_time = current_time + random_delay
    
    from discord_notifier import send_discord_embed
    
    await save_last_posted_time(bot_name, current_time, {
        "post_count": posts_made, 
        "next_post_time": new_next_post_time
    })
    
    LOG.info(f"Post made successfully. Total posts: {posts_made}.")
    LOG.info(f"Next post will be around {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_next_post_time))}. Exiting.")
    
    send_discord_embed(
        title="🤖 New Thread Posted!",
        description=f"> {post[0]}",
        fields=[{"name": "Next Scheduled Post", "value": f"<t:{int(new_next_post_time)}:R> (approx)", "inline": False}],
        color=0x9b59b6
    )


if __name__ == "__main__":
    setup_logging()
    LOG.info("Starting bot run...")
    main_func()
