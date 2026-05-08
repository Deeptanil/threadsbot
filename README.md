# Autonomous Threads AI Bot

> **Note:** This project began as a fork of [jiri-otoupal/threadsBot](https://github.com/jiri-otoupal/threadsBot). It has since been heavily re-engineered into a fully autonomous, serverless social media engine. Huge thanks to the original author for the foundational architecture!

This repository contains a highly advanced AI bot designed to automatically post viral content to Threads and authentically engage with fans in the comments. It runs entirely for free in the cloud using GitHub Actions and the Google Gemini API.

---

## 🔥 Key Features

- **Gemini AI Engine:** Uses Google's `gemini-3.1-flash-lite-preview` for high-quality, conversational, and "un-corporate" post generation.
- **Recursive Auto-Replies:** The bot doesn't just reply once—it traverses deep comment threads, engaging in multi-layer conversations with users just like a real human.
- **Context Memory:** When generating a reply, the AI reads the entire conversation history leading up to the comment so it never loses track of the context.
- **Discord Rich Notifications:** Connects to a Discord Webhook to stream beautifully formatted, color-coded live updates whenever a new thread is posted or an auto-reply is triggered.
- **3-Strike Error Recovery:** If the AI API goes down due to high traffic, the bot intelligently tracks failed tasks and retries them later. If a task fails 3 times, it is safely skipped without breaking the bot.
- **Serverless & Stateless:** Runs on a free 15-minute GitHub Actions schedule. State is persisted natively via JSON files committed back to the repository, requiring zero external databases.
- **Anti-Spam Bypassing:** Uses randomized posting delays (2-3.5 hours) and offset cron triggers to avoid triggering GitHub or Meta rate limits.
- **Multi-Account Support:** Natively supports running multiple Threads accounts completely in parallel with customized personalities and offset cron schedules.

---

## 🎭 Multi-Account Support

This bot is fully designed to run multiple Threads accounts simultaneously without them interfering with each other. 

By default, the repository contains 3 workflow files:
- `threads-bot.yml` (Account 1)
- `threads-bot-2.yml` (Account 2)
- `threads-bot-3.yml` (Account 3)

**To set up multiple accounts:**
1. Open the `roles/` folder. You will find `account1.txt`, `account2.txt`, and `account3.txt`. Edit these files to give each bot a completely unique personality and posting topic.
2. In your GitHub repository settings, add the API keys for the additional accounts using the prefixes:
   - `ACCOUNT2_ACCESS_TOKEN`, `ACCOUNT2_USER_ID`, etc.
   - `ACCOUNT3_ACCESS_TOKEN`, `ACCOUNT3_USER_ID`, etc.
3. The GitHub Action workflows are pre-configured to run 5 minutes apart to avoid Git push collisions, ensuring smooth 24/7 operation for all 3 accounts.

---

## 🛠️ Requirements

- Python 3.11 or higher
- Long-lived Threads User Access Token
- Google Gemini API Key
- Discord Webhook URL (Optional)

---

## 🚀 Installation & Deployment (GitHub Actions)

This bot is designed to run automatically via GitHub Actions in the background 24/7.

1. Create a Threads app in the Meta Developer Dashboard and generate a long-lived User Access Token.
2. Fork or upload this repository to your own GitHub account.
3. Go to your repository's **Settings > Secrets and variables > Actions**.
4. Add the following repository secrets:
   - `THREADS_ACCESS_TOKEN`: Your long-lived Threads token.
   - `THREADS_USER_ID`: Your Threads Account ID.
   - `THREADS_APP_ID`: Your Meta App ID.
   - `THREADS_API_SECRET`: Your Meta App Secret.
   - `GOOGLE_API_KEY`: Your Gemini API Key.
   - `DISCORD_WEBHOOK_URL`: (Optional) Your Discord channel webhook.
5. Go to **Settings > Actions > General > Workflow permissions** and ensure **Read and write permissions** is selected. This is CRITICAL because the bot now automatically refreshes its own tokens and saves them back to the repository.
6. The bot will now run automatically! It proactively refreshes its tokens every 24 hours to ensure zero downtime.

---

## 💻 Local Usage

If you prefer to test the bot locally on your machine:

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
   DISCORD_WEBHOOK_URL=your_discord_webhook
   ```
3. Run the bot manually:
   ```bash
   python main.py account1
   ```

---

## License

This project is licensed under the specific License. See the `LICENSE` file for details.

---

Did you find the original project useful?
<br>
Please support the original creator's work here:
<br>
<a href="https://www.buymeacoffee.com/jiriotoupal" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy me a Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>