import asyncio
import json
import time
from pathlib import Path

import aiofiles

def get_data_file(bot_name: str) -> Path:
    return Path(f"data-{bot_name}.json")


async def load_last_posted_time(bot_name: str) -> dict:
    """Loads the last posted time and additional data from a JSON file."""
    data_file = get_data_file(bot_name)
    if not data_file.exists():
        current_time = time.time()
        await save_last_posted_time(bot_name, current_time, {})
        return {"last_posted_time": current_time}

    async with aiofiles.open(data_file, mode="r") as file:
        content = await file.read()
        data = json.loads(content)
    return data


async def save_last_posted_time(bot_name: str, timestamp: float, additional_data: dict) -> None:
    """Saves the current timestamp as the last posted time and merges additional data."""
    data_file = get_data_file(bot_name)
    if data_file.exists():
        content = await asyncio.to_thread(data_file.read_text)
        existing_data = json.loads(content)
    else:
        existing_data = {}

    existing_data.update(additional_data)
    existing_data["last_posted_time"] = timestamp
    await asyncio.to_thread(data_file.write_text, json.dumps(existing_data))
