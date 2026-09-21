[![View All Projects](https://img.shields.io/badge/View_All_Projects-omdika.github.io-blue?style=flat-square&logo=github)](https://omdika.github.io/)

# Telegram iOS Development AI Agent

<img width="502" height="367" alt="image" src="https://github.com/user-attachments/assets/10238247-5747-4e12-8305-afd18dafadb1" />


An AI-powered Telegram coding agent connected to **Google Cloud Vertex AI (Gemini)** for automating iOS development with **Swift and SwiftUI** directly through GitHub pull requests.

The agent is designed to help iOS developers turn natural-language instructions, screenshots, and UI references into production-ready code changes. It can inspect an existing iOS codebase, update or create Swift files, and open a pull request for review—all from Telegram.

## ✨ What This iOS AI Agent Can Do

- Understand iOS development tasks written in natural language.
- Analyze screenshots and UI references sent through Telegram.
- Scan and understand an existing Swift/SwiftUI codebase.
- Create and modify Swift, SwiftUI, networking, model, view, and configuration files.
- Follow the project’s existing architecture, naming conventions, and coding style.
- Reuse existing components and avoid unnecessary duplicate code.
- Stream AI progress and status updates back to Telegram.
- Create a dedicated Git branch and pull request for every task.
- Let the user review and merge the generated iOS changes from Telegram.
- Cache the codebase snapshot during an active session to reduce repeated scans and improve response time.

> This project is focused primarily on iOS development. Backend repository support remains available when configured, but the main workflow and examples are intended for Swift and SwiftUI projects.

---

## 🔄 Bot Workflow

The agent follows a structured workflow from receiving an iOS instruction to creating a pull request:

```text
[Telegram User]
       │
       ├─► Send a development request, screenshot, or UI reference
       │
[Debouncer: 2.5 seconds]
       └─► Combines consecutive text messages and multiple images
       │
[execute_task: per-user lock]
       └─► Prevents conflicting tasks from running at the same time
       │
[Workspace Sync]
       └─► Clones or updates the configured repository and creates a task branch
       │
[iOS Codebase Scan & Cache]
       └─► Scans relevant Swift and SwiftUI files and caches the session snapshot
       │
[Vertex AI: Gemini 2.5 Flash]
       └─► Processes the instruction, codebase snapshot, and screenshots
       │
[Streaming Telegram Status]
       └─► Sends AI progress and implementation details in real time
       │
[Code Parser & Writer]
       └─► Creates or updates files in the local workspace
       │
[Git Push & Pull Request]
       └─► Commits changes, pushes the task branch, and creates a GitHub PR
       │
[User Review & Merge]
       └─► Review and merge the iOS pull request from Telegram
       │
[Reset]
       └─► Clears the session cache when the task is complete or reset
```

### Workflow Details

1. **Message Debouncing and Media Handling**  
   When text and screenshots are sent as separate messages, the bot waits **2.5 seconds** before processing them. This allows multiple messages and images to be combined into one complete iOS development request.

2. **Session Lock and Repository Synchronization**  
   Each user has an execution lock to prevent concurrent tasks from modifying the same workspace. The bot synchronizes the configured repository from the `main` branch and creates a dedicated task branch such as `ai-task-<message_id>`.

3. **Swift/SwiftUI Codebase Snapshot**  
   On the first request, the bot scans relevant files in the iOS project, such as Swift source files, SwiftUI views, models, services, and configuration files. The scan runs in a separate thread so the bot remains responsive. The snapshot is cached for the active session and reused by subsequent requests.

4. **AI Analysis and Code Generation**  
   Vertex AI receives the user’s instruction, the cached codebase snapshot, and any attached screenshots. Gemini analyzes the existing implementation before generating changes that fit the project’s architecture and style.

5. **Code Writing and Pull Request Creation**  
   The agent parses the generated response, writes the requested changes to the workspace, commits the changes, pushes the task branch, and creates a GitHub pull request when code changes are detected.

6. **Review and Merge**  
   The user can review the generated iOS changes in GitHub and use the Telegram action button to merge the pull request. After merging, the session cache can be cleared to start with a fresh codebase snapshot.

---

## 🛠️ Requirements and Setup

### 1. Create a Telegram Bot and Get Your User ID

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the instructions to create a bot.
3. Save the **Telegram Bot Token** for your `.env` file.
4. Search for **@userinfobot**, send any message, and copy your numeric Telegram User ID.
5. The bot uses this ID to restrict access to authorized users.

---

### 2. Configure a GitHub Personal Access Token

The bot needs GitHub access to clone repositories, create branches, push commits, open pull requests, and merge pull requests.

1. Open GitHub **Settings** → **Developer settings** → **Personal access tokens**.
2. Create a classic token or a fine-grained token.
3. Grant the minimum permissions required by your repository. For a classic token, this commonly includes:
   - `repo` for private repository access, commits, pull requests, and merges.
   - `workflow` only if the repository workflows need to be updated or triggered through the token.
4. Copy the token and store it as `GITHUB_TOKEN` in `.env`.

Never commit your token to the repository.

---

### 3. Configure Google Cloud Vertex AI

This project uses the `google-genai` SDK with Vertex AI to process text instructions and screenshots.

#### Create a GCP Project and Enable Vertex AI

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project or select an existing project.
3. Copy the **Project ID**.
4. Search for **Vertex AI API** and enable it.

#### Create a Service Account

1. Go to **IAM & Admin** → **Service Accounts**.
2. Click **Create Service Account**.
3. Give it a name, such as `telegram-ios-ai-agent`.
4. Grant the **Vertex AI User** role: `roles/aiplatform.user`.
5. Create a JSON key from the service account’s **Keys** tab.
6. Store the key securely, for example as `gcp-key.json`.

**Never commit the JSON key to GitHub.**

#### Authenticate Locally

You can authenticate using either of these methods.

**Option 1: Use a service account JSON key**

```env
GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/gcp-key.json"
```

**Option 2: Use the Google Cloud CLI**

```bash
gcloud auth application-default login
```

The Google SDK will automatically use the application default credentials.

---

## 📝 Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Then configure the required values:

```env
# Telegram Configuration
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
ALLOWED_TELEGRAM_USER_ID=123456789

# GitHub Configuration
GITHUB_TOKEN="your_github_personal_access_token"
IOS_REPO="your-username-or-org/your-ios-repository"

# Optional backend repository support
BACKEND_REPO="your-username-or-org/your-backend-repository"

# Workspace and Google Cloud Configuration
WORKSPACE_DIR="./workspace"
GCP_PROJECT_ID="your-gcp-project-id"

# Optional: service account credentials
GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/gcp-key.json"
```

For an iOS-only setup, `IOS_REPO` is the primary repository setting. Leave `BACKEND_REPO` empty if backend support is not needed.

---

## 🚀 Running the Agent

### Option A: Run Locally

1. Create and activate a Python 3.10+ virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   # Windows: venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start the bot:

   ```bash
   python bot.py
   ```

### Option B: Run with Docker

Make sure Docker and Docker Compose are installed, then run:

```bash
docker-compose up -d --build
```

View the logs:

```bash
docker-compose logs -f
```

---

## 💡 Telegram Commands

Send these commands directly to the bot:

- `/start` — Start interacting with the bot and verify user authorization.
- `/reset` or `/new` — Clear the active conversation and remove the cached iOS codebase snapshot. Use this before starting a new task that should be based on a fresh `main` branch.

### Example iOS Requests

You can send requests such as:

- “Build this screen in SwiftUI based on the attached screenshot.”
- “Add loading, empty, and error states to the profile view.”
- “Refactor this UIKit screen into SwiftUI while preserving the existing behavior.”
- “Add an async/await API service for the existing user endpoint.”
- “Fix the navigation issue and add a preview for this view.”
- “Create a reusable SwiftUI component that matches the attached design.”

The agent will inspect the existing project before making changes and will provide the implementation through a GitHub pull request for review.

---

## 🔐 Security Notes

- Keep Telegram, GitHub, and Google Cloud credentials in `.env` or a secure secret manager.
- Never commit `.env`, service account JSON files, or access tokens.
- Restrict Telegram access with `ALLOWED_TELEGRAM_USER_ID`.
- Use the minimum GitHub token permissions required for your repositories.
- Review generated code and pull requests before merging them into your iOS project.
