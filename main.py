import asyncio
import logging
import random
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

    current_time = time.time()
    
    LOG.info(f"Posting to Threads: {post[0]}")
    await post_to_threads(post[0], creds_file)
    
    last_posted_time = await load_last_posted_time()
    posts_made = last_posted_time.get("post_count", 0) + 1
    
    await save_last_posted_time(current_time, {"post_count": posts_made})
    
    LOG.info(f"Post made successfully. Total posts: {posts_made}. Exiting.")


if __name__ == "__main__":
    setup_logging()
    print("Starting bot...")
    main_func()
