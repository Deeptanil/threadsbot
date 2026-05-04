import json
import logging
import os
import time
import asyncio
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Dict, Tuple, List

from google import genai
from dotenv import load_dotenv

from text_constants import role_desc

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

# Initialize Gemini client
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


# ✅ Generate posts using Gemini
async def generate_posts_batch(text, override_role=None) -> List[Dict]:
    for attempt in range(3):  # retry up to 3 times
        try:
            prompt = f"""
            {role_desc if override_role is None else override_role}

            Write 5 short, raw, relatable Threads posts.

            Return ONLY valid JSON in this format:
            [
                {{"post": "text here", "predicted_reach": 0-100}}
            ]

            Topic: {text}
            """

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )

            raw = response.text.strip()

            # Clean markdown if Gemini adds ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]

            data = json.loads(raw)

            LOG.info(f"Generated {len(data)} posts")
            return data

        except Exception as e:
            LOG.error(f"Retry {attempt+1} due to error: {e}")
            await asyncio.sleep(20)

    return []


# ✅ Evaluate comment for auto-reply
async def evaluate_comment_for_reply(comment_text: str, override_role=None) -> Dict:
    for attempt in range(3):
        try:
            prompt = f"""
            {role_desc if override_role is None else override_role}

            You are evaluating a comment left on your Threads post.
            The comment is: "{comment_text}"

            Evaluate if this comment is positive, interactive, and good for your account.
            Do NOT reply if it's negative, hateful, spam, or a generic bot-like comment.
            If it is good, generate a short, human-like, authentic response.
            If an interactable question can be asked organically, include it. Otherwise, keep it a simple, short reply (sometimes just a thank youuuu).

            Return ONLY valid JSON in this format:
            {{
                "should_reply": true or false,
                "reply_text": "your response here, or empty string if false"
            }}
            """

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )

            raw = response.text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines)
            
            # Clean up potential "json" prefix inside block
            if raw.startswith("json\n"):
                raw = raw[5:]

            data = json.loads(raw)
            return data
        except Exception as e:
            LOG.error(f"Reply eval retry {attempt+1} due to error: {e}")
            await asyncio.sleep(5)
            
    return {"should_reply": False, "reply_text": ""}


# ✅ Save posts to file
async def save_batch(name: str, batch: List[Dict]):
    if not batch:
        return

    complete = {"t": time.time(), "posts": batch}

    with open(f"posts-{name}.json", "w", encoding="utf-8") as f:
        json.dump(complete, f, indent=4)


# ✅ Get next post
async def get_next_post(name: str) -> Tuple[str, datetime, float] | None:
    filename = f"posts-{name}.json"
    filepath = Path(filename)

    if not filepath.is_file():
        raise FileNotFoundError(f"{filename} not found")

    with filepath.open("r") as file:
        data = json.load(file)

    timestamp = datetime.fromtimestamp(data["t"])
    posts = data["posts"]

    if not posts:
        LOG.info("No posts left")
        return None

    selected_post = posts[randint(0, len(posts) - 1)]

    posts.remove(selected_post)

    reach = selected_post.get("predicted_reach", 0)
    selected_post.pop("predicted_reach", None)

    # Save updated list
    with filepath.open("w") as file:
        json.dump(data, file, indent=4)

    return selected_post["post"], timestamp, reach


# ✅ Check if posts file exists
async def posts_exist(name):
    return Path(f"posts-{name}.json").is_file()


# 🔥 TEST RUN
if __name__ == "__main__":
    async def test():
        posts = await generate_posts_batch("building something from scratch")

        if not posts:
            print("❌ No posts generated (rate limit or error). Try again later.")
            return

        await save_batch("test", posts)

        next_post = await get_next_post("test")
        print("✅ Next post:", next_post)

    asyncio.run(test())