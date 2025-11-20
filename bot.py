import os
import threading
import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
from flask import Flask

# Fix Tesseract path for Render/Docker
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ================== CONFIG ==================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in Render environment variables!")

CHANNEL_A_ID = 1428424023435513876   # Screenshots channel
CHANNEL_B_ID = 1428424076162240702   # Leaderboard channel
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
leaderboard = {}  # {user_id: (best_score, image_url, display_name)}
leaderboard_message = None

# ----------------- OCR HELPERS -----------------
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    candidates = [
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2),
        cv2.threshold(cv2.bitwise_not(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ]
    best_text = ""
    for c in candidates:
        text = pytesseract.image_to_string(c, config='--psm 6')
        if len(text) > len(best_text):
            best_text = text
    return best_text

def extract_score_and_name(text):
    # Find all numbers (supports commas, dots, spaces)
    numbers = re.findall(r'\d{1,3}(?:[.,\s]?\d{3})*(?:[.,]\d+)?', text)
    numbers = [int(n.replace(',', '').replace('.', '').replace(' ', '')) 
               for n in numbers if n.replace(',', '').replace('.', '').replace(' ', '').isdigit()]
    if not numbers:
        return None, None
    score = max(numbers)
    if score < 10:  # Lowered for testing (change back to 100 later if you want)
        return None, None

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    name = next((l[:30] for l in lines 
                 if len(l) > 2 and str(score) not in l 
                 and not l.replace(' ', '').replace('.', '').replace(',', '').isdigit()), None)
    return score, name or "Unknown Player"

# ----------------- LEADERBOARD UPDATE -----------------
async def update_leaderboard():
    global leaderboard_message
    channel = bot.get_channel(CHANNEL_B_ID)
    if not channel:
        print(f"[ERROR] Could not find leaderboard channel {CHANNEL_B_ID}")
        return

    if not leaderboard:
        embed = discord.Embed(title="Top 20 Leaderboard", 
                            description="No valid scores yet!", color=0x2f3136)
    else:
        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Top 20 Leaderboard", color=0x00ff00)
        for rank, (uid, (score, url, name)) in enumerate(sorted_lb, 1):
            member = bot.get_user(uid)
            display = member.display_name if member else name
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
            embed.add_field(name=f"{medal} **{score:,}**", value=f"[{display}]({url})", inline=False)
        embed.set_footer(text=f"{len(leaderboard)} total entries • Auto-updated")
        embed.timestamp = discord.utils.utcnow()

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel.send(embed=embed)
            await leaderboard_message.pin()
    except Exception as e:
        print(f"[ERROR] Leaderboard edit failed: {e}")

# ----------------- DISCORD EVENTS -----------------
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user} | OCR ready!")
    await update_leaderboard()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return await bot.process_commands(message)

    for att in message.attachments:
        if not att.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp', 'gif')):
            continue

        try:
            data = await att.read()
            nparr = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                await message.add_reaction("❌")
                continue

            text = preprocess_image(img)
            score, name = extract_score_and_name(text)

            if not score:
                await message.add_reaction("❓")
                continue

            old = leaderboard.get(message.author.id, (0, "", ""))[0]
            if score > old:
                leaderboard[message.author.id] = (score, att.url, message.author.display_name)
                await message.add_reaction("📈")
            else:
                await message.add_reaction("✅")

            await update_leaderboard()

        except Exception as e:
            print(f"[ERROR] OCR failed: {e}")
            await message.add_reaction("❌")

    await bot.process_commands(message)

@bot.command()
@commands.has_permissions(administrator=True)
async def refresh(ctx):
    await update_leaderboard()
    await ctx.send("Leaderboard refreshed!", delete_after=5)

# ----------------- FLASK (keeps Render alive) -----------------
app = Flask(__name__)
@app.route('/')
def home():
    return "OCR Leaderboard Bot is running!", 200

def run_bot():
    bot.run(TOKEN)

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
