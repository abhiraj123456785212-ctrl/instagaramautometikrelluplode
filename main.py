import os
import yt_dlp
import subprocess
import json
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("short_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}

YOUTUBE_REGEX = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"

# START
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("👋 Send YouTube Link")

# HANDLE LINK
@app.on_message(filters.private & filters.text)
async def get_link(client, message):

    # ❌ ignore commands (/start etc)
    if message.text.startswith("/"):
        return

    url = message.text.strip()

    # ✅ VALIDATE LINK
    if not re.match(YOUTUBE_REGEX, url):
        return await message.reply("❌ Send valid YouTube link")

    user_id = message.from_user.id
    user_data[user_id] = {"url": url}

    # DELETE USER MESSAGE (clean UI)
    try:
        await message.delete()
    except:
        pass

    await client.send_message(user_id, "🔍 Fetching formats...")

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats", [])

    # ❌ REMOVE 144p (as per your requirement)
    allowed = ["240p", "360p", "480p", "720p", "1080p"]

    quality_dict = {}

    for f in formats:
        if f.get("height"):
            q = f"{f['height']}p"
            if q in allowed:
                quality_dict[q] = f["format_id"]

    if not quality_dict:
        return await message.reply("❌ No valid quality found")

    user_data[user_id]["formats"] = quality_dict

    # BUTTON UI
    buttons = []
    for q in quality_dict:
        buttons.append([InlineKeyboardButton(q, callback_data=f"q_{q}")])

    await client.send_message(
        user_id,
        "📥 Select Quality:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# BUTTON CLICK
@app.on_callback_query(filters.regex("^q_"))
async def quality_selected(client, callback_query):

    user_id = callback_query.from_user.id
    quality = callback_query.data.split("_")[1]

    data = user_data.get(user_id)
    if not data:
        return await callback_query.message.reply("❌ Send link first")

    url = data["url"]
    format_id = data["formats"].get(quality)

    await callback_query.message.edit("⏬ Downloading...")

    ydl_opts = {
        "format": f"{format_id}+bestaudio/best",
        "outtmpl": "video.mp4",
        "merge_output_format": "mp4",
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    await callback_query.message.edit("✂️ Creating Shorts...")

    # ✅ GET DURATION (SAFE METHOD)
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "video.mp4"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        data_json = json.loads(result.stdout)
        duration = float(data_json["format"]["duration"])
    except:
        await client.send_message(user_id, "❌ Error reading video duration")
        return

    start = 0
    part = 1

    while start < duration:
        output = f"part{part}.mp4"

        # ⚡ FAST + HIGH QUALITY SHORTS
        cmd = f'ffmpeg -i video.mp4 -ss {start} -t 60 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" -c:v libx264 -preset veryfast -crf 28 -c:a aac -y {output}'
        subprocess.call(cmd, shell=True)

        await client.send_video(user_id, output, caption=f"🎬 Part {part}")

        os.remove(output)

        start += 60
        part += 1

    os.remove("video.mp4")

    await client.send_message(user_id, "✅ Done!")

# RUN
app.run()
