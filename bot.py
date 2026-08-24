import os
import io
import time
import asyncio
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from github import Github
from git import Repo
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_TELEGRAM_USER_ID", "0"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BACKEND_REPO_NAME = os.getenv("BACKEND_REPO", os.getenv("GITHUB_REPO", ""))
IOS_REPO_NAME = os.getenv("IOS_REPO", "")
BASE_WORKSPACE = os.getenv("WORKSPACE_DIR", "./workspace")

BACKEND_DIR = os.path.join(BASE_WORKSPACE, "backend")
IOS_DIR = os.path.join(BASE_WORKSPACE, "ios")

ai_client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID", "ivory-oarlock-482401-n5"),
    location="us-central1"
)

gh = Github(GITHUB_TOKEN)
gh_backend_repo = gh.get_repo(BACKEND_REPO_NAME) if BACKEND_REPO_NAME else None
gh_ios_repo = gh.get_repo(IOS_REPO_NAME) if IOS_REPO_NAME else None

user_sessions = dict()
user_locks = dict()
user_message_queues = dict()


def scan_repo_files(repo_path: str, repo_label: str) -> str:
    if not os.path.exists(repo_path):
        return ""
    context = list()
    ignore_dirs = {
        ".git", "__pycache__", "venv", ".venv", "node_modules", ".pytest_cache", 
        ".build", "DerivedData", "Assets.xcassets", "Pods", ".xcodeproj", ".xcworkspace"
    }
    allowed_exts = (".py", ".swift", ".json", ".yaml", ".yml", ".md", ".sql", "Dockerfile")
    
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith(allowed_exts) or file == "Dockerfile":
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if len(content) < 50000:
                            context.append(f"--- [{repo_label.upper()}] FILE: {rel_path} ---\n" + content + "\n")
                except Exception:
                    pass
    return "\n".join(context)


async def apply_ai_changes_streaming(user_id: int, prompt: str, images_bytes_list: list, status_msg, context: ContextTypes.DEFAULT_TYPE) -> str:
    backend_context = scan_repo_files(BACKEND_DIR, "backend")
    ios_context = scan_repo_files(IOS_DIR, "ios") if IOS_REPO_NAME else "No iOS repo configured."

    system_instruction = (
        "Kamu adalah Senior Fullstack AI Engineer handal (Python Backend & iOS Swift/SwiftUI).\n"
        "Kamu mengelola 2 repository: [BACKEND] dan [IOS].\n"
        "Analisis gambar/screenshot dan sesuaikan kode yang dibutuhkan.\n\n"
        "ATURAN FORMAT OUTPUT UNTUK FILE BARU/EDIT:\n"
        "Untuk Backend:\n"
        "REPO: backend\n"
        "FILE: path/ke/file.py\n"
        "```python\n"
        "# isi lengkap file\n"
        "```\n\n"
        "Untuk iOS Frontend:\n"
        "REPO: ios\n"
        "FILE: AppName/Views/SampleView.swift\n"
        "```swift\n"
        "# isi lengkap file\n"
        "```\n\n"
        "Jika prompt HANYA diskusi atau analisis tanpa perlu perubahan kode, berikan penjelasan ringkas dan JANGAN buat blok REPO:/FILE:."
    )

    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "history": list(),
            "active_branch": None
        }

    history = user_sessions[user_id]["history"]
    current_text = (
        f"[BACKEND CODEBASE SNAPSHOT]:\n{backend_context}\n\n"
        f"[IOS CODEBASE SNAPSHOT]:\n{ios_context}\n\n"
        f"[USER INSTRUCTION]:\n{prompt}"
    )

    parts = [types.Part.from_text(text=current_text)]
    if images_bytes_list:
        for img_bytes in images_bytes_list:
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    contents = list()
    for item in history:
        contents.append(item)
    contents.append(types.Content(role="user", parts=parts))

    # Gunakan STREAMING API dari Vertex AI
    response_stream = ai_client.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        ),
    )

    raw_text = ""
    last_edit_time = time.time()
    chunk_count = 0

    for chunk in response_stream:
        if chunk.text:
            raw_text += chunk.text
            chunk_count += 1
            
            # Update status di Telegram setiap 2 detik agar tidak kena rate limit
            if time.time() - last_edit_time > 2.0:
                last_edit_time = time.time()
                lines = raw_text.strip().splitlines()
                last_line = lines[-1][:80] if lines else ""
                try:
                    await status_msg.edit_text(
                        f"🧠 [2/4] Vertex AI sedang streaming kode...\n"
                        f"📊 Total respon: {len(raw_text)} karakter\n"
                        f"✍️ Menulis: `{last_line}...`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    history.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
    history.append(types.Content(role="model", parts=[types.Part.from_text(text=raw_text)]))

    if len(history) > 16:
        user_sessions[user_id]["history"] = history[-16:]

    # Parsing pembuatan file ke disk lokal
    sections = raw_text.split("REPO:")
    explanation = sections.pop(0).strip() if sections else raw_text
    prefixes = ("python\n", "swift\n", "yaml\n", "json\n", "text\n", "dockerfile\n", "markdown\n")

    for sec in sections:
        sec_lines = sec.strip().splitlines()
        if not sec_lines:
            continue
        target_repo_type = sec_lines.pop(0).strip().lower()
        sub_content = "\n".join(sec_lines)
        
        target_base_dir = BACKEND_DIR if "backend" in target_repo_type else IOS_DIR
        
        file_blocks = sub_content.split("FILE:")
        for fb in file_blocks:
            fb_lines = fb.strip().splitlines()
            if not fb_lines:
                continue
            rel_file_path = fb_lines.pop(0).strip()
            code_str = "\n".join(fb_lines)
            
            if "```" in code_str:
                parts_code = code_str.split("```")
                if len(parts_code) > 1:
                    file_content = parts_code.pop(1)
                    if file_content.startswith(prefixes):
                        file_content = file_content.split("\n", 1).pop(1)
                else:
                    file_content = code_str
            else:
                file_content = code_str

            target_file = Path(target_base_dir) / rel_file_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(file_content.strip() + "\n")

    return explanation if explanation else raw_text


def sync_repo(repo_name: str, target_dir: str):
    if not repo_name:
        return None
    remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{repo_name}.git"
    if not os.path.exists(target_dir):
        Repo.clone_from(remote_url, target_dir)
    repo = Repo(target_dir)
    repo.git.checkout("main")
    repo.git.pull()
    return repo


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Akses ditolak.")
        return
    await update.message.reply_text("👋 Halo! AI Agent siap dengan Real-time Streaming Logs.")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        return
    user_sessions.pop(user_id, None)
    await update.message.reply_text("🔄 Sesi & Memori di-reset!")


async def execute_task(chat_id: int, user_id: int, prompt: str, images: list, message_id: int, context: ContextTypes.DEFAULT_TYPE):
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    
    async with lock:
        img_info = f" ({len(images)} gambar)" if images else ""
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔄 [1/4] Menyiapkan branch & sinkronisasi repo{img_info}..."
        )

        try:
            session = user_sessions.setdefault(user_id, {"history": list(), "active_branch": None})
            if not session["active_branch"]:
                backend_git = sync_repo(BACKEND_REPO_NAME, BACKEND_DIR)
                ios_git = sync_repo(IOS_REPO_NAME, IOS_DIR) if IOS_REPO_NAME else None

                branch_name = f"ai-task-{message_id}"
                if backend_git:
                    b_branch = backend_git.create_head(branch_name)
                    b_branch.checkout()
                if ios_git:
                    i_branch = ios_git.create_head(branch_name)
                    i_branch.checkout()
                session["active_branch"] = branch_name
            else:
                branch_name = session["active_branch"]
                backend_git = Repo(BACKEND_DIR) if os.path.exists(BACKEND_DIR) else sync_repo(BACKEND_REPO_NAME, BACKEND_DIR)
                ios_git = Repo(IOS_DIR) if (IOS_REPO_NAME and os.path.exists(IOS_DIR)) else (sync_repo(IOS_REPO_NAME, IOS_DIR) if IOS_REPO_NAME else None)
                if backend_git:
                    backend_git.git.checkout(branch_name)
                if ios_git:
                    ios_git.git.checkout(branch_name)

            await status_msg.edit_text("🧠 [2/4] Terhubung ke Vertex AI GCP (Memulai Streaming)...")
            explanation = await apply_ai_changes_streaming(user_id, prompt, images, status_msg, context)

            backend_changed = backend_git and backend_git.is_dirty(untracked_files=True)
            ios_changed = ios_git and ios_git.is_dirty(untracked_files=True)

            if not backend_changed and not ios_changed:
                preview_exp = explanation[:3900] + ("..." if len(explanation) > 3900 else "")
                await status_msg.edit_text(f"💡 Hasil Analisis AI:\n\n{preview_exp}")
                return

            await status_msg.edit_text("📦 [3/4] Commit & Push branch ke GitHub...")
            keyboard = list()

            if backend_changed:
                backend_git.git.add(A=True)
                backend_git.git.commit("-m", f"feat(ai-backend): {prompt[:50]}")
                backend_git.git.push("--set-upstream", "origin", branch_name)
                
                existing = list(gh_backend_repo.get_pulls(state="open", head=f"{gh_backend_repo.owner.login}:{branch_name}"))
                pr_backend = existing.pop(0) if existing else gh_backend_repo.create_pull(
                    title=f"🤖 Backend AI: {prompt[:50]}",
                    body=f"Perubahan Backend otomatis oleh AI.\n\nPrompt:\n> {prompt}",
                    head=branch_name,
                    base="main",
                )
                keyboard.append([
                    InlineKeyboardButton("🔍 PR Backend", url=pr_backend.html_url),
                    InlineKeyboardButton("✅ Merge Backend", callback_data=f"merge_be_{pr_backend.number}")
                ])

            if ios_changed and gh_ios_repo:
                ios_git.git.add(A=True)
                ios_git.git.commit("-m", f"feat(ai-ios): {prompt[:50]}")
                ios_git.git.push("--set-upstream", "origin", branch_name)

                existing_ios = list(gh_ios_repo.get_pulls(state="open", head=f"{gh_ios_repo.owner.login}:{branch_name}"))
                pr_ios = existing_ios.pop(0) if existing_ios else gh_ios_repo.create_pull(
                    title=f"🤖 iOS AI: {prompt[:50]}",
                    body=f"Perubahan iOS otomatis oleh AI.\n\nPrompt:\n> {prompt}",
                    head=branch_name,
                    base="main",
                )
                keyboard.append([
                    InlineKeyboardButton("🔍 PR iOS", url=pr_ios.html_url),
                    InlineKeyboardButton("✅ Merge iOS", callback_data=f"merge_ios_{pr_ios.number}")
                ])

            summary_note = explanation[:300] + ("..." if len(explanation) > 300 else "")
            await status_msg.edit_text(
                f"✅ Tugas Selesai!\n\n"
                f"🌿 Branch: {branch_name}\n"
                f"📝 Ringkasan:\n{summary_note}\n\n"
                f"Silakan review & merge PR masing-masing:",
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )

        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    chat_id = update.effective_chat.id
    message = update.message

    text_part = message.caption if message.photo else message.text
    img_bytes = None
    if message.photo:
        photo_file = await message.photo[-1].get_file()
        img_bytes = bytes(await photo_file.download_as_bytearray())

    if user_id not in user_message_queues:
        user_message_queues[user_id] = {
            "texts": list(),
            "images": list(),
            "chat_id": chat_id,
            "message_id": message.message_id,
            "timer_task": None
        }

    queue = user_message_queues[user_id]
    if text_part:
        queue["texts"].append(text_part)
    if img_bytes:
        queue["images"].append(img_bytes)

    if queue["timer_task"] and not queue["timer_task"].done():
        queue["timer_task"].cancel()

    async def delayed_trigger():
        await asyncio.sleep(2.5)
        if user_id in user_message_queues:
            item = user_message_queues.pop(user_id)
            final_prompt = "\n".join(item["texts"]) if item["texts"] else "Analisis gambar ini dan buat perbaikan kode."
            await execute_task(item["chat_id"], user_id, final_prompt, item["images"], item["message_id"], context)

    queue["timer_task"] = asyncio.create_task(delayed_trigger())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ALLOWED_USER_ID:
        return

    data = query.data
    try:
        if data.startswith("merge_be_"):
            pr_num = int(data.replace("merge_be_", ""))
            gh_backend_repo.get_pull(pr_num).merge(commit_message=f"Merged AI Backend PR #{pr_num}")
            await query.edit_message_text(f"🎉 PR Backend #{pr_num} berhasil di-merge!")
        elif data.startswith("merge_ios_"):
            pr_num = int(data.replace("merge_ios_", ""))
            gh_ios_repo.get_pull(pr_num).merge(commit_message=f"Merged AI iOS PR #{pr_num}")
            await query.edit_message_text(f"🎉 PR iOS #{pr_num} berhasil di-merge!")
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal merge: {str(e)}")


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("new", reset_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    
    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), handle_incoming))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 AI Agent siap dengan Real-time Streaming & Log Monitor...")
    app.run_polling()


if __name__ == "__main__":
    main()
