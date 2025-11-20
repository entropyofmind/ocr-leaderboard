import os
import threading
import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
from flask import Flask

# Tesseract path for Render/Docker
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ================== CONFIG ==================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing!")

CHANNEL_A_ID = 1428424023435513876   # Where people post screenshots
CHANNEL_B_ID = 1428424076162240702   # Leaderboard channel

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
leaderboard = {}        # normalized_name: (best_score, original_name)
leaderboard_message = None

# ----------------- BEST PREPROCESSING FOR YOUR GAME -----------------
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Slight resize up helps OCR on small text
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    # Strong binarization + denoising
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # Remove small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return thresh

# ----------------- EXTRACT PLAYERS FROM YOUR EXACT LAYOUT -----------------
def extract_players(text):
    players = []
    # Split into lines and clean
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        next_line = lines[i + 1]

        # Name line: usually contains letters and no huge number
        if re.search(r'[A-Za-z]', line) and not re.search(r'\d{7}', line):
            # Score line: contains "Damage Points:" or just huge number
            score_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', next_line)
            if score_match:
                name = re.sub(r'[^A-Za-z0-9_\-\[\]]', '', line).strip()[:20]
                if name:  # avoid empty names
                    score = int(score_match.group(1).replace(',', ''))
                    players.append((name.lower(), score, name))
            # Also try same-line format (some screenshots)
            else:
                score_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', line)
                if score_match:
                    name_part = line.split(score_match.group(1))[0].strip()
                    name = re.sub(r'[^A-Za-z0-9_\-\[\]]', '', name_part)[:20]
                    if name:
                        score = int(score_match.group(1).replace(',', ''))
                        players.append((name.lower(), score, name))
        i += 1
    return players

# ----------------- PROCESS ONE IMAGE -----------------
async def process_image(data):
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    preprocessed = preprocess_image(img)
    text = pytesseract.image_to_string(preprocessed, config='--psm 6')
    return extract_players(text)

# ----------------- UPDATE LEADERBOARD EMBED -----------------
async def update_leaderboard():
    global leaderboard_message
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        return

    if not leaderboard:
        embed = discord.Embed(title="Top 20 Damage Ranking", description="No data yet!", color=0x2f3136)
    else:
        top20 = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Top 20 Damage Ranking", color=0x00ff00)
        medals = ["1st_place_medal", "2nd_place_medal", "3rd_place_medal"] + [f"{i}." for i in range(4,21)]
        for i, (norm, (score, name)) in enumerate(top20):
            embed.add_field(
                name=f"{medals[i]} **{score:,}**",
                value=f"`{name}`",
                inline=False
            )
        embed.set_footer(text=f"Total tracked: {len(leaderboard)} players • Updated")
        embed.timestamp = discord.utils.utcnow()

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel.send(embed=embed)
            await leaderboard_message.pin()
    except Exception as e:
        print(f"Embed error: {e}")

# ----------------- REBUILD FROM HISTORY ON STARTUP -----------------
async def rebuild_from_history():
    print("Rebuilding leaderboard from last 500 screenshots...")
    channel = bot.get_channel(CHANNEL_A_ID)
    count = 0
    async for msg in channel.history(limit=500):
        if msg.attachments:
            for att in msg.attachments:
                if att.filename.lower().split('.')[-1] in {'png','jpg','jpeg','webp'}:
                    try:
                        data = await att.read()
                        players = await process_image(data)
                        for norm, score, name in players:
                            if score > leaderboard.get(norm, (0, ""))[0]:
                                leaderboard[norm] = (score, name)
                        count += 1
                    except:
                        pass
    print(f"Rebuilt from {count} images → {len(leaderboard)} players tracked")
    await update_leaderboard()

# ----------------- EVENTS -----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online — Hunting Trap Damage Leaderboard ready!")
    await rebuild_from_history()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    updated = False
    valid = False

    for att in message.attachments:
        if att.filename.lower().split('.')[-1] in {'png','jpg','jpeg','webp'}:
            try:
                data = await att.read()
                players = await process_image(data)
                if players:
                    valid = True
                    for norm, score, name in players:
                        if score > leaderboard.get(norm, (0, ""))[0]:
                            leaderboard[norm] = (score, name)
                            updated = True
            except Exception as e:
                print(f"OCR error: {e}")

    if valid:
        await message.add_reaction("chart_with_upwards_trend" if updated else "white_check_mark")
        await update_leaderboard()
    else:
        await message.add_reaction("question")

    await bot.process_commands(message)

@bot.command()
@commands.has_permissions(administrator=True)
async def rebuild(ctx):
    await ctx.send("Rebuilding from history...")
    await rebuild_from_history()
    await ctx.send("Done!")

# ----------------- FLASK (Render keep-alive) -----------------
app = Flask(__name__)
@app.route('/')
def home():
    return "Hunting Trap Damage Leaderboard • Running", 200

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.run(TOKEN), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
