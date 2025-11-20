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
    raise RuntimeError("DISCORD_TOKEN not set in Render!")

CHANNEL_A_ID = 1428424023435513876   # Screenshots channel
CHANNEL_B_ID = 1428424076162240702   # Leaderboard channel

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Global leaderboard: normalized_name → (best_score, display_name)
leaderboard = {}
leaderboard_message = None

# ----------------- IMAGE PREPROCESSING -----------------
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return thresh

# ----------------- EXTRACT PLAYERS -----------------
def extract_items(text):
    players = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(r'[A-Za-z]', line) and not re.search(r'^\d+$', line):
            full_line = line + " " + (lines[i+1] if i+1 < len(lines) else "")
            match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', full_line)
            if match:
                score = int(match.group(1).replace(',', ''))
                if score >= 100:
                    name = re.sub(r'[^A-Za-z0-9_\-\[\] ]', '', line).strip()
                    if name and len(name) >= 2:
                        norm_name = name.lower()
                        players.append((norm_name, score, name[:20]))
        i += 1
    return players

async def process_image(data):
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    preprocessed = preprocess_image(img)
    text = pytesseract.image_to_string(preprocessed, config='--psm 6')
    return extract_items(text)

# ----------------- UPDATE LEADERBOARD -----------------
async def update_leaderboard():
    global leaderboard_message
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        return

    if not leaderboard:
        embed = discord.Embed(
            title="Hunting Trap Damage Ranking",
            description="No screenshot posted yet!",
            color=0x2f3136
        )
    else:
        top20 = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Hunting Trap Damage Ranking", color=0x00ff00)
        medals = ["1st_place_medal", "2nd_place_medal", "3rd_place_medal"] + [f"{i}." for i in range(4,21)]
        for i, (norm, (score, name)) in enumerate(top20):
            embed.add_field(
                name=f"{medals[i]} **{score:,}**",
                value=f"`{name}`",
                inline=False
            )
        embed.set_footer(text=f"Tracking {len(leaderboard)} players • Live updated")
        embed.timestamp = discord.utils.utcnow()

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel.send(embed=embed)
            await leaderboard_message.pin()
            async for msg in channel.history(limit=1):
                if msg.type == discord.MessageType.pins_add:
                    await msg.delete()
    except Exception as e:
        print(f"Leaderboard update error: {e}")

# ----------------- EVENTS -----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online — Hunting Trap Leaderboard ready!")
    await update_leaderboard()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    updated = False
    found_any = False

    for att in message.attachments:
        if att.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
            try:
                data = await att.read()
                players = await process_image(data)
                if players:
                    found_any = True
                    for norm_name, score, display_name in players:
                        old_score = leaderboard.get(norm_name, (0, ""))[0]
                        if score > old_score:
                            leaderboard[norm_name] = (score, display_name)
                            updated = True
            except Exception as e:
                print(f"Error processing image: {e}")

    # CORRECT EMOJI NAMES — NO MORE 10014/50035 ERRORS
    if found_any:
        if updated:
            await message.add_reaction("chart_increasing")      # New personal best
        else:
            await message.add_reaction("white_check_mark")      # Valid, no new high
        await update_leaderboard()
    else:
        await message.add_reaction("question")                  # Nothing detected

    await bot.process_commands(message)

# Optional: clear leaderboard
@bot.command()
@commands.has_permissions(administrator=True)
async def clearlb(ctx):
    global leaderboard, leaderboard_message
    leaderboard.clear()
    leaderboard_message = None
    await update_leaderboard()
    await ctx.send("Leaderboard cleared!", delete_after=5)

# ----------------- FLASK (Render keep-alive) -----------------
app = Flask(__name__)
@app.route('/')
def home():
    return "Hunting Trap Damage Leaderboard • Fully Operational", 200

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.run(TOKEN), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
