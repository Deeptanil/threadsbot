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
        You are a content safety filter for a brand's Threads account.
        Evaluate the following proposed post:
        "{post_text}"
        
        BLOCK the post ONLY if it meets ANY of these criteria:
        1. It is factually incoherent or complete nonsense.
        2. It contains hate speech, slurs, or directly attacks a specific real person or group with hostility.
        3. It promotes violence, self-harm, or illegal activity.
        
        IMPORTANT — Do NOT block posts that are:
        - Opinionated, provocative, or slightly controversial (this is intentional for engagement)
        - Critical of fashion trends, consumer habits, or industry norms
        - Edgy, bold, or designed to spark debate
        - Mildly sarcastic or dry in tone
        Engagement-driven content is the entire goal. Only block genuinely harmful content.
        
        Return ONLY valid JSON:
        {{"is_safe": true or false, "reason": "one sentence if false, else empty string"}}
        """
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )
        raw = response.text.strip()
        if raw.startswith("```"): raw = raw.split("```")[1]
        if raw.startswith("json\n"): raw = raw[5:]
        data = json.loads(raw)
        if not data.get("is_safe", False):
            LOG.info(f"Safety filter blocked post. Reason: {data.get('reason', 'unspecified')}")
        return data.get("is_safe", False)
    except Exception as e:
        LOG.error(f"Safety check failed: {e}")
        return False

# ✅ Generate posts using Gemini
async def generate_posts_batch(text, override_role=None, last_had_promo: bool = False) -> List[Dict]:
    for attempt in range(3):  # retry up to 3 times
        try:
            promo_instruction = (
                "The previous batch already included a promo post. Do NOT include a promo post in this batch."
                if last_had_promo else
                "If your role specifies a 1-in-5 promo rule, include exactly one promo post in this batch."
            )
            prompt = f"""
            {role_desc if override_role is None else override_role}

            Write exactly 5 Threads posts for this batch.

            FORMULA ROTATION RULES (critical for variety):
            - Each post MUST use a DIFFERENT trigger formula or approach from your role.
            - No two posts in this batch should use the same structure, format, or emotional angle.
            - Rotate across all available formulas: tribal splits, hot takes, shared frustrations, 
              lifestyle moments, soft callouts, niche identity posts, and (if applicable) one promo post.
            - Vary sentence length, line break usage, and whether or not you use a question.
            - {promo_instruction}

            Return ONLY valid JSON in this format:
            [
                {{"post": "text here", "predicted_reach": 0-100, "is_promo": true or false}}
            ]

            predicted_reach should honestly reflect how likely this specific post is to generate 
            replies and reach new users — score 90-100 only for posts with strong tribal or 
            controversial angles, 70-89 for solid relatable content, below 70 for safer posts.
            Set is_promo to true only for the post that mentions the brand website or product.
            """

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )

            raw = response.text.strip()

            # Clean markdown if Gemini adds ```
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines)
            if raw.startswith("json\n"):
                raw = raw[5:]

            data = json.loads(raw)
            
            safe_posts = []
            for item in data:
                is_safe = await evaluate_post_safety(item.get("post", ""), override_role)
                if is_safe:
                    safe_posts.append(item)
                else:
                    LOG.warning(f"Post failed safety filter: {item.get('post')}")

            # Sort by predicted_reach descending so the highest-confidence post always fires first
            safe_posts.sort(key=lambda x: x.get("predicted_reach", 0), reverse=True)

            LOG.info(f"Generated {len(safe_posts)} safe posts (out of {len(data)}). Top reach score: {safe_posts[0].get('predicted_reach') if safe_posts else 'N/A'}")
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

            CRITICAL PERSONA RULE: Every reply you write MUST sound exactly like the voice and persona
            described above. Do NOT reply generically. Do NOT sound like a helpful assistant.
            You are this specific account \u2014 reply as that person or brand would, in their exact tone.

            You are evaluating a comment left on your Threads account.
            Here is the full conversation history leading up to this point:
            "{parent_post_text}"

            The user just commented: "{comment_text}"

            Evaluate if this comment warrants a reply. Do NOT reply if the comment is:
            - Negative, hateful, or spam
            - A dead-end ("nice", "thanks", single emoji, one-word affirmation)
            - A generic bot-like comment with no conversation potential

            RULE: You MUST NEVER say "I followed you", "I followed you back", or promise to follow
            someone. You cannot press the follow button. Do not lie to users.

            If the comment warrants a response, write a short reply that sounds exactly like this
            account's persona. Keep it casual and on-brand. Ask a follow-up question only if it
            feels completely natural \u2014 don't force it.

            RULE: If the comment is a business inquiry, order issue, or needs human judgment,
            set "needs_review" to true and provide a "suggested_reply" for the human to edit.

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
async def peek_next_post(name: str) -> Tuple[str, float, bool] | None:
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
    return selected_post["post"], selected_post.get("predicted_reach", 0), selected_post.get("is_promo", False)

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
        post_text, reach, is_promo = res
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