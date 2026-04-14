import os
import yt_dlp
import subprocess
import json
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("short_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}

# ================= AUTO DELETE =================
async def auto_delete(file, delay=600):
    await asyncio.sleep(delay)
    if os.path.exists(file):
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except:
            pass

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("👋 Send YouTube Link")

# ================= HANDLE LINK =================
@app.on_message(filters.text & filters.private & ~filters.command(["start"]))
async def get_link(client, message):

    if not message.text:
        return

    url = message.text.strip()

    if not ("youtube.com" in url or "youtu.be" in url):
        return

    user_id = message.from_user.id
    user_data[user_id] = {"url": url}

    try:
        await message.delete()
    except:
        pass

    msg = await message.reply("🔍 Fetching video info...")

    try:
        with yt_dlp.YoutubeDL() as ydl:
            info = ydl.extract_info(url, download=False)
    except:
        return await msg.edit("❌ Failed to fetch video")

    formats = info.get("formats", [])

    allowed = ["144p", "240p", "360p", "480p", "720p", "1080p"]
    quality_dict = {}

    for f in formats:
        if f.get("height"):
            q = f"{f['height']}p"
            if q in allowed:
                quality_dict[q] = f["format_id"]

    if not quality_dict:
        return await msg.edit("❌ No valid quality found")

    user_data[user_id]["formats"] = quality_dict

    buttons = []
    for q in quality_dict:
        buttons.append([InlineKeyboardButton(q, callback_data=f"q_{q}")])

    await msg.edit(
        "📥 Select Quality:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ================= BUTTON CLICK =================
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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except:
        return await callback_query.message.edit("❌ Download failed")

    # auto delete original
    asyncio.create_task(auto_delete("video.mp4", 600))

    await callback_query.message.edit("✂️ Creating Shorts...")

    # ================= GET DURATION =================
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
        return await client.send_message(user_id, "❌ Error reading video duration")

    # ================= SPLIT VIDEO =================
    start = 0
    part = 1

    while start < duration:

        # last part fix
        remaining = duration - start
        clip_time = 60 if remaining > 60 else remaining

        output = f"part{part}.mp4"

        # ✅ NO CUT VERSION (FULL VIDEO)
        cmd = f'ffmpeg -i video.mp4 -ss {start} -t {clip_time} -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" -y {output}'
        subprocess.call(cmd, shell=True)

        try:
            await client.send_video(user_id, output, caption=f"🎬 Part {part}")
        except:
            pass

        if os.path.exists(output):
            os.remove(output)

        start += 60
        part += 1

    await client.send_message(user_id, "✅ Done!")

# ================= RUN =================
app.run()
