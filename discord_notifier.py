import os
import requests
import logging

LOG = logging.getLogger(__name__)

def send_discord_embed(title: str, description: str = "", fields: list = None, color: int = 0x3498db):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        LOG.debug("No DISCORD_WEBHOOK_URL provided. Skipping notification.")
        return

    try:
        embed = {
            "title": title,
            "description": description,
            "color": color
        }
        if fields:
            embed["fields"] = fields
            
        data = {
            "embeds": [embed]
        }
        response = requests.post(webhook_url, json=data)
        if response.status_code not in [200, 204]:
            LOG.error(f"Failed to send Discord notification: {response.status_code} {response.text}")
    except Exception as e:
        LOG.error(f"Error sending Discord notification: {e}")
