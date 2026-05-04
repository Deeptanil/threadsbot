# Threads Bot (Gemini & GitHub Actions Fork)

> **Note:** This project is a fork of the original [jiri-otoupal/threadsBot](https://github.com/jiri-otoupal/threadsBot). Huge thanks to the original author for the foundational architecture!

This repository contains a bot designed to automatically post highly engaging, viral content to Threads. It has been heavily modified from the original repository to run entirely for free in the cloud using GitHub Actions and the Google Gemini API.

---

## Changes in this Fork
- **Gemini AI Integration:** Switched from OpenAI's ChatGPT to Google's GenAI SDK (`gemini-3.1-flash-lite-preview`) for cost-effective, high-quality post generation.
- **GitHub Actions Deployment:** Removed the 24/7 local loop. The script now executes once and gracefully exits, making it 100% compatible with free GitHub Actions cron schedules.
- **Simplified Authentication:** Removed the complex OAuth callback server. The bot now directly uses a long-lived Threads User Access Token loaded securely from environment variables, eliminating the need for SSL certificates.
- **Viral Prompt Engineering:** Completely rewrote `text_constants.py` to instruct the AI to write in an authentic, "un-corporate," and highly conversational tone optimized specifically for the Threads algorithm.

---

## Requirements

- Python 3.11 or higher
- Dependencies specified in `requirements.txt`
- Long-lived Threads User Access Token
- Google Gemini API Key

---

## Installation & Deployment (GitHub Actions)

This bot is designed to run automatically via GitHub Actions every 2 hours.

1. Create a Threads app in the Meta Developer Dashboard and generate a long-lived User Access Token.
2. Fork or upload this repository to your own GitHub account.
3. Go to your repository's **Settings > Secrets and variables > Actions**.
4. Add the following repository secrets:
   - `THREADS_ACCESS_TOKEN`: Your long-lived Threads token.
   - `THREADS_USER_ID`: Your Threads Account ID.
   - `THREADS_APP_ID`: Your Meta App ID.
   - `THREADS_API_SECRET`: Your Meta App Secret.
   - `GOOGLE_API_KEY`: Your Gemini API Key.
5. Go to **Settings > Actions > General > Workflow permissions** and ensure "Read and write permissions" is selected so the bot can save its state.
6. The bot will now run automatically! You can also trigger it manually from the "Actions" tab.

---

## Local Usage

If you prefer to test the bot locally:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the root directory:
   ```env
   THREADS_APP_ID=your_app_id
   THREADS_API_SECRET=your_app_secret
   THREADS_ACCESS_TOKEN=your_long_lived_token
   THREADS_USER_ID=your_user_id
   GOOGLE_API_KEY=your_gemini_key
   ```
3. Run the bot:
   ```bash
   python main.py <bot_name>
   ```

---

## License

This project is licensed under the specific License. See the `LICENSE` file for details.

---

Did you find the original project useful?
<br>
<br>
Please support the original creator's work here:
<br>
<a href="https://www.buymeacoffee.com/jiriotoupal" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy me a Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>