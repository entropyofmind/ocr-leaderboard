import os
import asyncio
import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
from datetime import datetime, timezone
from flask import Flask

# ====================================================
# CONFIG
# ====================================================

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set!")

# CHANNELS
CHANNEL_A_ID = 1428424023435513876   # Screenshots
CHANNEL_B_ID = 1428424076162240702   # Leaderboard

# EMOJIS
EMOJI_GOLD = "🥇"
EMOJI_VALID = "✅"
EMOJI_FAIL = "❌"

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

leaderboard = {}  # normalized_name → (best_score, display_name)
leaderboard_message = None


# ====================================================
# OCR PROCESSING
# ====================================================

def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)


def extract_players(text):
    """
    Extract (name, score) pairs from OCR text.
    More tolerant and handles numbers without commas.
    """
    players = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0

    score_regex = r"(\d{3,}(?:,\d{3})*)"

    while i < len(lines):
        line = lines[i]

        # Require text with letters to count as "name-ish"
        if re.search(r"[A-Za-z]", line):
            combined = line + " " + (lines[i + 1] if i + 1 < len(lines) else "")
            match = re.search(score_regex, combined)

            if match:
                score = int(match.group(1).replace(",", ""))
                if score >= 100:
                    clean_name = re.sub(r"[^A-Za-z0-9_\-\[\] ]", "", line).strip()
                    if clean_name and len(clean_name) >= 2:
                        players.append((clean_name.lower(), score, clean_name[:20]))

        i += 1

    return players


async def process_image(data: bytes):
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return []

    processed = preprocess_image(img)
    text = pytesseract.image_to_string(processed, config="--psm 6")

    return extract_players(text)


# ====================================================
# LEADERBOARD
# ====================================================

async def update_leaderboard():
    global leaderboard_message

    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        print("Leaderboard channel not found!")
        return

    if not leaderboard:
        embed = discord.Embed(
            title="Hunting Trap Damage Ranking",
            description="No screenshot detected yet.",
            color=0x2f3136
        )
    else:
        embed = discord.Embed(
            title="Hunting Trap Damage Ranking",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )

        # TOP 20
        top20 = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]

        medals = ["🥇", "🥈", "🥉"]

        for i, (norm, (score, display_name)) in enumerate(top20):
            medal = medals[i] if i < 3 else f"{i+1}."
            embed.add_field(
                name=f"{medal} **{score:,}**",
                value=f"`{display_name}`",
                inline=False
            )

        embed.set_footer(text=f"Tracking {len(leaderboard)} players")

    # Edit or send leaderboard message
    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel.send(embed=embed)
            await leaderboard_message.pin()

            # remove auto "X pinned a message"
            async for m in channel.history(limit=1):
                if m.type == discord.MessageType.pins_add:
                    await m.delete()

    except Exception as e:
        print(f"Error updating embed: {e}")


# ====================================================
# EVENTS
# ====================================================

@bot.event
async def on_ready():
    print(f"{bot.user} is now online.")
    await asyncio.sleep(2)
    await update_leaderboard()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    found_any = False
    updated_any = False

    for attachment in message.attachments:
        if not attachment.filename.lower().endswith(("png", "jpg", "jpeg", "webp")):
            continue

        try:
            data = await attachment.read()
            players = await process_image(data)

            if players:
                found_any = True
                for norm, score, name in players:
                    old_score = leaderboard.get(norm, (0, ""))[0]
                    if score > old_score:
                        leaderboard[norm] = (score, name)
                        updated_any = True

        except Exception as e:
            print(f"OCR processing error: {e}")

    # Reactions
    if found_any:
        if updated_any:
            await message.add_reaction(EMOJI_GOLD)
        else:
            await message.add_reaction(EMOJI_VALID)
    else:
        await message.add_reaction(EMOJI_FAIL)

    if found_any:
        await update_leaderboard()

    await bot.process_commands(message)


# ====================================================
# FLASK SERVER
# ====================================================

app = Flask(__name__)

@app.get("/")
def home():
    return "Bot is running!", 200


async def start_bot():
    await bot.start(TOKEN)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
