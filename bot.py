import os
import asyncio
import json
from datetime import datetime, timezone
from io import BytesIO

import discord
from discord.ext import commands
from flask import Flask, request, jsonify

import pytesseract
import cv2
import numpy as np
import re

# ---------------------------
# CONFIG - update as needed
# ---------------------------
# Ensure this path matches tesseract binary inside the container
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "/usr/bin/tesseract")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set!")

# Channel ids (integers). Make sure these match your server.
CHANNEL_A_ID = int(os.environ.get("CHANNEL_A_ID", 1428424023435513876))
CHANNEL_B_ID = int(os.environ.get("CHANNEL_B_ID", 1428424076162240702))

# Test image path (the file you uploaded is available at /mnt/data/bt.webp in this environment)
SAMPLE_IMAGE_PATH = os.environ.get("SAMPLE_IMAGE", "/mnt/data/bt.webp")

# Emojis
EMOJI_GOLD = "🥇"
EMOJI_VALID = "✅"
EMOJI_FAIL = "❌"

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory leaderboard (norm_name -> (best_score, display_name))
leaderboard = {}
leaderboard_message = None

# ---------------------------
# OCR helpers
# ---------------------------
def preprocess_image(img):
    """Grayscale, upscale, threshold and morphology for Tesseract."""
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # upscale for small text
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    # adaptive threshold
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return processed

def extract_players(text):
    """
    Extract player name lines and scores.
    Looks for a text line with letters (candidate name), and a nearby number with commas.
    Returns list of tuples: (normalized_name, score_int, display_name)
    """
    players = []
    if not text:
        return players

    # Clean: collapse multiple spaces, standardize newlines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Regex: accept numbers like 1,234 or 1234 (we look for groups of >=3 digits)
    score_regex = re.compile(r"(\d{3,}(?:,\d{3})*|\d{4,})")

    i = 0
    while i < len(lines):
        line = lines[i]
        # require alphabetic char in the name line
        if re.search(r"[A-Za-z]", line):
            # try to find number in same line or next line
            combined = line + " " + (lines[i+1] if i + 1 < len(lines) else "")
            m = score_regex.search(combined)
            if m:
                score_text = m.group(1)
                # remove commas
                try:
                    score = int(score_text.replace(",", ""))
                except ValueError:
                    i += 1
                    continue
                # filter low scores (adjust threshold if needed)
                if score >= 100:
                    # sanitize name: keep letters, digits, underscore, hyphen, spaces
                    display = re.sub(r"[^A-Za-z0-9_\-\[\] ]+", "", line).strip()
                    display = " ".join(display.split())  # collapse extra spaces
                    if display and len(display) >= 2:
                        norm = display.lower()
                        players.append((norm, score, display[:40]))
        i += 1

    return players

async def process_image_bytes(data: bytes):
    """Decode image bytes, preprocess, OCR, and extract players."""
    try:
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            print("[OCR] cv2.imdecode returned None")
            return []
        proc = preprocess_image(img)
        if proc is None:
            print("[OCR] preprocess_image returned None")
            return []
        # Tesseract config: single block, allow digits & letters
        raw = pytesseract.image_to_string(proc, config="--psm 6")
        print(f"[OCR] Raw text:\n{raw}")
        players = extract_players(raw)
        print(f"[OCR] Extracted players: {players}")
        return players
    except Exception as e:
        print(f"[OCR] Exception in process_image_bytes: {e}")
        return []

# ---------------------------
# Leaderboard and posting
# ---------------------------
async def update_leaderboard_message():
    """Create or edit the pinned leaderboard message in CHANNEL_B_ID."""
    global leaderboard_message
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        print(f"[Leaderboard] Channel {CHANNEL_B_ID} not found.")
        return

    if not leaderboard:
        embed = discord.Embed(
            title="Hunting Trap Damage Ranking",
            description="No screenshot detected yet.",
            color=0x2f3136,
            timestamp=datetime.now(timezone.utc)
        )
    else:
        embed = discord.Embed(
            title="Hunting Trap Damage Ranking",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        top = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        medals = ["🥇", "🥈", "🥉"]
        for i, (norm, (score, display_name)) in enumerate(top):
            medal = medals[i] if i < 3 else f"{i+1}."
            embed.add_field(name=f"{medal} **{score:,}**", value=f"`{display_name}`", inline=False)
        embed.set_footer(text=f"Tracking {len(leaderboard)} players")

    try:
        if leaderboard_message:
            print("[Leaderboard] Editing existing leaderboard message...")
            await leaderboard_message.edit(embed=embed)
        else:
            print("[Leaderboard] Sending new leaderboard message...")
            leaderboard_message = await channel.send(embed=embed)
            # pin and remove pinned system message
            await leaderboard_message.pin()
            async for m in channel.history(limit=2):
                if m.type == discord.MessageType.pins_add:
                    try:
                        await m.delete()
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Leaderboard] Exception when updating leaderboard: {e}")

async def apply_players_to_leaderboard(players):
    """Update leaderboard dict with found players. Return (found_any, updated_any)."""
    found_any = False
    updated_any = False
    for norm, score, display in players:
        found_any = True
        old_score = leaderboard.get(norm, (0, ""))[0]
        if score > old_score:
            leaderboard[norm] = (score, display)
            updated_any = True
            print(f"[Leaderboard] New high for {display}: {score} (prev {old_score})")
        else:
            print(f"[Leaderboard] Found {display} with {score} but did not beat {old_score}")
    return found_any, updated_any

async def post_results_to_channel(players, origin="upload"):
    """Send a small embed to CHANNEL_B with the parsing results."""
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        print("[Post] Target channel not found.")
        return

    if not players:
        embed = discord.Embed(title="OCR Result", description="No players found in image.", color=0xff6666,
                              timestamp=datetime.now(timezone.utc))
    else:
        text = "\n".join([f"• `{name}` — **{score:,}**" for _, score, name in players])
        embed = discord.Embed(title=f"OCR Result ({origin})", description=text, color=0x88ff88,
                              timestamp=datetime.now(timezone.utc))
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[Post] Failed to send results embed: {e}")

# ---------------------------
# Discord events
# ---------------------------
@bot.event
async def on_ready():
    print(f"[Discord] Bot logged in as: {bot.user} (id: {bot.user.id})")
    # ensure the channel objects become available
    await asyncio.sleep(1)
    # Try to fetch existing leaderboard message (optional enhancement)
    # We'll just ensure the leaderboard message exists after startup
    try:
        await update_leaderboard_message()
    except Exception as e:
        print(f"[Discord] error during initial leaderboard update: {e}")

@bot.event
async def on_message(message: discord.Message):
    # ignore other bots
    if message.author.bot:
        return

    print(f"[Discord] message received in channel {getattr(message.channel, 'id', None)} from {message.author}: attachments={len(message.attachments)}")

    # Only process messages sent in CHANNEL_A_ID that contain attachments
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    found_any = False
    updated_any = False

    for att in message.attachments:
        print(f"[Discord] Attachment filename: {att.filename} content_type={att.content_type}")
        # accept common image extensions
        if not att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            print(f"[Discord] Skipping attachment with unsupported extension: {att.filename}")
            continue
        try:
            data = await att.read()
            players = await process_image_bytes(data)
            f, u = await apply_players_to_leaderboard(players)
            found_any = found_any or f
            updated_any = updated_any or u
        except Exception as e:
            print(f"[Discord] Exception processing attachment: {e}")

    # react to the original message to show result
    try:
        if found_any:
            if updated_any:
                await message.add_reaction(EMOJI_GOLD)
            else:
                await message.add_reaction(EMOJI_VALID)
        else:
            await message.add_reaction(EMOJI_FAIL)
    except Exception as e:
        print(f"[Discord] Failed to add reaction: {e}")

    if found_any:
        await update_leaderboard_message()

    await bot.process_commands(message)

# ---------------------------
# Flask webserver (upload endpoints)
# ---------------------------
app = Flask(__name__)

@app.get("/")
def home():
    return "Bot running!", 200

@app.post("/upload")
def upload_image():
    """
    POST /upload
    form-data: file=<binary image> OR image=<binary image>
    This endpoint will:
      - perform OCR
      - update leaderboard if players are found
      - post a result embed to the leaderboard channel
    """
    # DEBUG logging
    print("[HTTP] /upload called")
    file = None
    if "file" in request.files:
        file = request.files["file"]
    elif "image" in request.files:
        file = request.files["image"]
    else:
        # maybe raw body
        if request.data:
            data = request.data
            # process raw bytes synchronously by scheduling to bot loop
            loop = asyncio.get_event_loop()
            fut = asyncio.run_coroutine_threadsafe(_handle_upload_bytes(data), loop)
            res = fut.result(timeout=10)
            return jsonify(res), 200
        return jsonify({"ok": False, "error": "No file part"}), 400

    data = file.read()
    loop = asyncio.get_event_loop()
    try:
        fut = asyncio.run_coroutine_threadsafe(_handle_upload_bytes(data), loop)
        res = fut.result(timeout=15)
        return jsonify(res), 200
    except Exception as e:
        print(f"[HTTP] Exception scheduling OCR task: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/test_process")
def test_process():
    """
    Test route that processes the SAMPLE_IMAGE_PATH inside the container.
    Useful to validate end-to-end OCR -> Discord posting without uploading a file.
    """
    print("[HTTP] /test_process called")
    if not os.path.exists(SAMPLE_IMAGE_PATH):
        return jsonify({"ok": False, "error": f"Sample image not found at {SAMPLE_IMAGE_PATH}"}), 404
    with open(SAMPLE_IMAGE_PATH, "rb") as f:
        data = f.read()
    loop = asyncio.get_event_loop()
    try:
        fut = asyncio.run_coroutine_threadsafe(_handle_upload_bytes(data, origin="test_process"), loop)
        res = fut.result(timeout=20)
        return jsonify(res), 200
    except Exception as e:
        print(f"[HTTP] test_process scheduling error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------------
# Async handlers (run on bot loop)
# ---------------------------
async def _handle_upload_bytes(data: bytes, origin="upload"):
    """
    Runs on the bot's asyncio loop.
    Returns a dict with status and list of players found.
    """
    print(f"[OCR] Handling image bytes (origin={origin}), size={len(data)} bytes")
    players = await process_image_bytes(data)
    found_any, updated_any = await apply_players_to_leaderboard(players)
    # Post results to channel (non-blocking)
    try:
        await post_results_to_channel(players, origin=origin)
        await update_leaderboard_message()
    except Exception as e:
        print(f"[OCR] Exception posting/updating leaderboard: {e}")
    return {"ok": True, "found": found_any, "updated": updated_any, "players": [{"name": p[2], "score": p[1]} for p in players]}

# ---------------------------
# Entrypoint
# ---------------------------
async def _start_bot():
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"[Discord] Bot start exception: {e}")

if __name__ == "__main__":
    # NOTE: ensure you enabled Message Content Intent in the Discord developer portal.
    print("[Startup] Starting bot and Flask server...")
    loop = asyncio.get_event_loop()
    # Start the Discord client as a background task on the loop
    loop.create_task(_start_bot())

    # Run Flask (blocking) in the main thread, binding to $PORT for Render
    port = int(os.environ.get("PORT", 10000))
    # Flask's built-in server is fine here because Render runs the Docker container; logs go to stdout.
    app.run(host="0.0.0.0", port=port)
