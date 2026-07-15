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

async def evaluate_batch_safety(posts: List[str]) -> List[bool]:
    if not posts:
        return []
    try:
        posts_formatted = "\n".join(f"[{i}]: {p}" for i, p in enumerate(posts))
        prompt = f"""
        You are a content safety filter for a brand's Threads account.
        Evaluate the following proposed posts:
        
        {posts_formatted}
        
        BLOCK a post ONLY if it meets ANY of these criteria:
        1. It is factually incoherent or complete nonsense.
        2. It contains hate speech, slurs, or directly attacks a specific real person or group.
        3. It promotes violence, self-harm, or illegal activity.
        
        Do NOT block posts that are opinionated, controversial, critical of fashion, or sarcastic.
        
        Return ONLY valid JSON in this format:
        [
            {{"id": 0, "is_safe": true or false, "reason": "reason if false, else empty"}}
        ]
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
        if raw.startswith("json\n"):
            raw = raw[5:]
        
        data = json.loads(raw)
        safety_map = {item.get("id"): item.get("is_safe", False) for item in data}
        
        results = []
        for i in range(len(posts)):
            is_safe = safety_map.get(i, False)
            results.append(is_safe)
            if not is_safe:
                LOG.warning(f"Batch safety filter blocked post index {i}. Text: '{posts[i][:60]}'")
        return results
    except Exception as e:
        LOG.error(f"Batch safety check failed: {e}. Falling back to assuming all are safe.")
        return [True] * len(posts)

def _load_recent_posts(bot_name: str, limit: int = 20) -> List[str]:
    """Load the most recent posted texts from the performance log for a given bot."""
    import json as _json
    perf_file = f"performance-{bot_name}.json"
    if not os.path.exists(perf_file):
        return []
    try:
        with open(perf_file, "r", encoding="utf-8") as f:
            perf = _json.load(f)
        posts = perf.get("posts", [])
        # Sort by posted_at descending, take most recent N
        posts_sorted = sorted(posts, key=lambda x: x.get("posted_at", 0), reverse=True)
        return [p["text"].strip() for p in posts_sorted[:limit] if p.get("text")]
    except Exception as e:
        LOG.warning(f"Could not load recent posts for {bot_name}: {e}")
        return []

def _load_top_posts(bot_name: str, limit: int = 3) -> List[str]:
    """Load the best performing posted texts from the performance log for style emulation."""
    import json as _json
    perf_file = f"performance-{bot_name}.json"
    if not os.path.exists(perf_file):
        return []
    try:
        with open(perf_file, "r", encoding="utf-8") as f:
            perf = _json.load(f)
        posts = perf.get("posts", [])
        if not posts:
            return []
        
        # Calculate an engagement score: views + replies * 10 + likes * 5
        def score(p):
            views = p.get("views") or 0
            replies = p.get("replies") or 0
            likes = p.get("likes") or 0
            return views + (replies * 10) + (likes * 5)
            
        posts_scored = sorted(posts, key=score, reverse=True)
        # Select the top N distinct posts
        seen = set()
        top_posts = []
        for p in posts_scored:
            text = p.get("text", "").strip()
            if text and text not in seen and score(p) > 0:
                seen.add(text)
                top_posts.append(text)
                if len(top_posts) >= limit:
                    break
        return top_posts
    except Exception as e:
        LOG.warning(f"Could not load top posts for {bot_name}: {e}")
        return []


# ✅ Generate posts using Gemini
async def generate_posts_batch(text, override_role=None, last_had_promo: bool = False, bot_name: str = "") -> List[Dict]:
    for attempt in range(3):  # retry up to 3 times
        try:
            # --- Build the "recently posted" anti-repetition block ---
            recent_posts = _load_recent_posts(bot_name) if bot_name else []
            if recent_posts:
                recent_block = "\n".join(f'  - "{p}"' for p in recent_posts)
                history_section = f"""
            RECENTLY POSTED CONTENT — DO NOT REPEAT OR CLOSELY REWRITE ANY OF THESE:
            The following posts have already been published on this account in the last few weeks.
            You MUST NOT write about the same topics, use the same angles, or produce similar phrasing.
            Treat this list as a hard blacklist:
{recent_block}
"""
            else:
                history_section = ""

            # --- Build the closed-loop "top performing" emulation block ---
            top_posts = _load_top_posts(bot_name) if bot_name else []
            if top_posts:
                top_block = "\n".join(f'  - "{p}"' for p in top_posts)
                top_performing_section = f"""
            TOP PERFORMING POSTS ON THIS ACCOUNT (EMULATE THIS STYLE & TOPIC DEPTH):
            These posts performed exceptionally well on this account. Emulate the engagement-trigger
            angles, formatting, and tone:
{top_block}
"""
            else:
                top_performing_section = ""

            active_role = role_desc if override_role is None else override_role

            prompt = f"""
            {active_role}

            {history_section}

            {top_performing_section}

            Write exactly 5 Threads posts for this batch.

            FORMULA ROTATION RULES (critical for variety):
            - Each post MUST use a DIFFERENT trigger formula or approach from your role.
            - No two posts in this batch should use the same structure, format, or emotional angle.
            - Rotate across all available formulas: tribal splits, hot takes, shared frustrations, 
              lifestyle moments, soft callouts, niche identity posts, and founder voice posts.
            - Vary sentence length, line break usage, and whether or not you use a question.
            - ALL 5 posts MUST have "is_promo": false. There are no promotional posts in the feed — ever.

            ABSOLUTE URL BAN (CRITICAL — ZERO EXCEPTIONS):
            - Do NOT include any URL, domain name, website address, "link in bio", or any variation.
            - This includes: prettiva.co, strayed.in, strayed.club, or ANY other domain.
            - Posts containing links will receive ZERO views due to the Threads algorithm. Do not do this.

            Return ONLY valid JSON in this format:
            [
                {{"post": "text here", "predicted_reach": 0-100, "is_promo": false}}
            ]

            predicted_reach should honestly reflect how likely this specific post is to generate 
            replies and reach new users — score 90-100 only for posts with strong tribal or 
            controversial angles, 70-89 for solid relatable content, below 70 for safer posts.
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
            
            # --- URL / domain filter — hard block, no exceptions ---
            # NOTE: Patterns are intentionally specific to avoid false positives on common words
            # (e.g. "coffee" contains ".co", "morning" contains ".in" — avoid substring-only matching)
            _URL_PATTERNS = [
                "http://", "https://", "www.",
                "prettiva.co", "strayed.in", "strayed.club",
                "link in bio", "link is in the bio", "link in my bio",
                "check the site", "check the link", "shop now",
                "shop at ", ".com/", ".in/", ".co/",
            ]

            candidates = []
            for item in data:
                post_text = item.get("post", "")
                post_lower = post_text.lower()

                # Block posts that sneak in a URL or domain despite instructions
                url_found = any(pattern in post_lower for pattern in _URL_PATTERNS)
                if url_found:
                    LOG.warning(f"URL ban stripped post from batch: '{post_text[:80]}'")
                    continue

                # Force is_promo to False regardless of what Gemini returned
                item["is_promo"] = False
                candidates.append(item)

            # --- Batch safety evaluation (Only 1 API call instead of 5) ---
            safe_posts = []
            if candidates:
                candidate_texts = [item.get("post", "") for item in candidates]
                safety_results = await evaluate_batch_safety(candidate_texts)
                for item, is_safe in zip(candidates, safety_results):
                    if is_safe:
                        safe_posts.append(item)
                    else:
                        LOG.warning(f"Post failed safety filter: {item.get('post', '')[:80]}")

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