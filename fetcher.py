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

async def evaluate_post_safety(post_text: str, override_role=None) -> bool:
    try:
        prompt = f"""
        You are a content safety filter for a brand account.
        Evaluate the following proposed post:
        "{post_text}"
        
        Is this post safe to publish? It must meet ALL three criteria:
        1. It makes logical sense.
        2. It is NOT aggressive or hostile.
        3. It is NOT harmful, offensive, or controversial.
        
        Return ONLY valid JSON:
        {{"is_safe": true or false}}
        """
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )
        raw = response.text.strip()
        if raw.startswith("```"): raw = raw.split("```")[1]
        data = json.loads(raw)
        return data.get("is_safe", False)
    except Exception as e:
        LOG.error(f"Safety check failed: {e}")
        return False

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
            
            safe_posts = []
            for item in data:
                is_safe = await evaluate_post_safety(item.get("post", ""), override_role)
                if is_safe:
                    safe_posts.append(item)
                else:
                    LOG.warning(f"Post failed safety filter: {item.get('post')}")

            LOG.info(f"Generated {len(safe_posts)} safe posts (out of {len(data)})")
            return safe_posts

        except Exception as e:
            LOG.error(f"Retry {attempt+1} due to error: {e}")
            await asyncio.sleep(20)

    return []


# ✅ Evaluate comment for auto-reply
async def evaluate_comment_for_reply(comment_text: str, override_role=None, parent_post_text="") -> Dict:
    for attempt in range(3):
        try:
            prompt = f"""
            {role_desc if override_role is None else override_role}

            You are evaluating a comment left on your Threads account.
            Here is the full conversation history leading up to this point:
            "{parent_post_text}"
            
            The user just commented: "{comment_text}"

            Evaluate if this comment is positive, interactive, and good for your account.
            Do NOT reply if it's negative, hateful, spam, or a generic bot-like comment.
            
            CRITICAL RULE 1: If the comment is a "conversation ender" (such as "you too", "thanks!", "have a great day", "haha", or just an emoji), do NOT reply. Return "should_reply": false. We do not want to force a reply when the conversation has naturally concluded!
            
            CRITICAL RULE 2: You MUST NEVER say "I followed you", "I followed you back", or promise to follow someone. You are a bot and cannot actually press the follow button. Do not lie to the users.

            If it is a good comment that warrants a response, generate a short, human-like, authentic response.
            If an interactable question can be asked organically, include it. Otherwise, keep it a simple, short reply.
            
            CRITICAL RULE 3: If the comment is highly complex, a business inquiry, requires customer support, or clearly needs human judgment, do NOT reply. Set "needs_review" to true and provide a "suggested_reply" for the human to edit.

            Return ONLY valid JSON in this format:
            {{
                "should_reply": true or false,
                "needs_review": true or false,
                "suggested_reply": "your draft response here, or empty string",
                "reply_text": "your auto-response here, or empty string if false or needs_review"
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
            
    return None


# ✅ Save posts to file
async def save_batch(name: str, batch: List[Dict]):
    if not batch:
        return

    complete = {"t": time.time(), "posts": batch}

    with open(f"posts-{name}.json", "w", encoding="utf-8") as f:
        json.dump(complete, f, indent=4)


# ✅ Peek at next post (without removing it)
async def peek_next_post(name: str) -> Tuple[str, float] | None:
    filename = f"posts-{name}.json"
    filepath = Path(filename)

    if not filepath.is_file():
        return None

    try:
        with filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except:
        return None

    posts = data.get("posts", [])
    if not posts:
        return None

    # We use index 0 as the "next" post to keep it consistent
    selected_post = posts[0]
    return selected_post["post"], selected_post.get("predicted_reach", 0)

# ✅ Remove a post by its text (called after successful posting)
async def remove_post(name: str, post_text: str):
    filename = f"posts-{name}.json"
    filepath = Path(filename)

    if not filepath.is_file():
        return

    try:
        with filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except:
        return

    posts = data.get("posts", [])
    new_posts = [p for p in posts if p.get("post") != post_text]
    data["posts"] = new_posts

    with filepath.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

# ✅ Get next post (Legacy - kept for compatibility but will be replaced in main.py)
async def get_next_post(name: str) -> Tuple[str, datetime, float] | None:
    res = await peek_next_post(name)
    if res:
        post_text, reach = res
        await remove_post(name, post_text)
        return post_text, datetime.now(), reach
    return None


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