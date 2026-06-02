import os
import tweepy
import logging
from dotenv import load_dotenv

load_dotenv()
LOG = logging.getLogger(__name__)

def post_to_x(text: str, bot_name: str = "account1"):
    prefix = bot_name.upper()
    api_key = os.getenv(f"{prefix}_X_API_KEY") or os.getenv("X_API_KEY")
    api_secret = os.getenv(f"{prefix}_X_API_SECRET") or os.getenv("X_API_SECRET")
    access_token = os.getenv(f"{prefix}_X_ACCESS_TOKEN") or os.getenv("X_ACCESS_TOKEN")
    access_secret = os.getenv(f"{prefix}_X_ACCESS_SECRET") or os.getenv("X_ACCESS_SECRET")
    
    if not all([api_key, api_secret, access_token, access_secret]) or api_key == "[ENTER_X_API_KEY]":
        LOG.warning(f"X credentials not fully configured for {bot_name}. Skipping X sync.")
        return False
        
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        
        response = client.create_tweet(text=text)
        LOG.info(f"Successfully posted to X for {bot_name}: {response.data}")
        return True
    except Exception as e:
        LOG.error(f"Failed to post to X for {bot_name}: {e}")
        return False

