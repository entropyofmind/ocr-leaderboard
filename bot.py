import os
import threading
import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
from flask import Flask

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ================== CONFIG ==================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set!")

CHANNEL_A_ID = 1428424023435513876   # Screenshots
CHANNEL_B_ID = 1428424076162240702   # Leaderboard

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

leaderboard = {}           # normalized_name → (best_score, display_name)
leaderboard_message = None

# ----------------- PREPROCESSING -----------------
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

# ----------------- EXTRACT PLAYERS -----------------
def extract_players(text):
    players = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(r'[A-Za-z]', line) and not re.search(r'^\d+$', line):
            full = line + " " + (lines[i+1] if i+1 < len(lines) else "")
            match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', full)
            if match:
                score = int(match.group(1).replace(',', ''))
                if score >= 100:
                    name = re.sub(r'[^A-Za-z0-9_\-\[\] ]', '', line).strip()
                    if name and len(name) >= 2:
                        players.append((name.lower(), score, name[:20]))
        i += 1
    return players

async def process_image(data):
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    text = pytesseract.image_to_string(preprocess_image(img), config='--psm 6')
    return extract_players(text)

# ----------------- UPDATE LEADERBOARD -----------------
async def update_leaderboard():
    global leaderboard_message
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        return

    if not leaderboard:
        embed = discord.Embed(title="Hunting Trap Damage Ranking", description="No screenshot yet!", color=0x2f3136)
    else:
        top20 = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Hunting Trap Damage Ranking", color=0x00ff00)
        for i, (norm, (score, name)) in enumerate(top20):
            medal = ["Gold medal", "Silver medal", "Bronze medal"][i] if i < 3 else f"{i+1}."
            embed.add_field(name=f"{medal} **{score:,}**", value=f"`{name}`", inline=False)
        embed.set_footer(text=f"Tracking {len(leaderboard)} players")
        embed.timestamp = discord.utils.utcnow()

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel.send(embed=embed)
            await leaderboard_message.pin()
            async for m in channel.history(limit=1):
                if m.type == discord.MessageType.pins_add:
                    await m.delete()
    except Exception as e:
        print(f"Embed error: {e}")

# ----------------- EVENTS -----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await update_leaderboard()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    updated = False
    found = False

    for att in message.attachments:
        if att.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
            try:
                data = await att.read()
                players = await process_image(data)
                if players:
                    found = True
                    for norm, score, name in players:
                        old = leaderboard.get(norm, (0, ""))[0]
                        if score > old:
                            leaderboard[norm] = (score, name)
                            updated = True
            except Exception as e:
                print(f"OCR error: {e}")

    # REAL UNICODE EMOJIS — COPY-PASTE THIS EXACTLY
    if found:
        if updated:
            await message.add_reaction("New high score!")   # Gold medal
        else:
            await message.add_reaction("Valid!")            # Check mark
    else:
        await message.add_reaction("Failed")                # Cross mark

    if found:
        await update_leaderboard()

    await bot.process_commands(message)

# ----------------- FLASK -----------------
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot running!", 200

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.run(TOKEN), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
