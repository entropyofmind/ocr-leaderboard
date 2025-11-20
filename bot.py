import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
import asyncio
import os

# ================== CONFIG ==================
CHANNEL_A_ID = 1428424023435513876   # ← CHANGE THIS — screenshots channel
CHANNEL_B_ID = 1428424076162240702   # ← CHANGE THIS — leaderboard channel
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

leaderboard = {}          # {user_id: (score, image_url, display_name)}
leaderboard_message = None

def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    inv = cv2.bitwise_not(gray)
    _, thresh_inv = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    candidates = [thresh1, thresh2, thresh_inv]
    best_text = ""
    for c in candidates:
        text = pytesseract.image_to_string(c, config='--psm 6')
        if len(text) > len(best_text):
            best_text = text
    return best_text

def extract_score_and_name(text):
    numbers = re.findall(r'\d{1,3}(?:[.,\s]?\d{3})*(?:[.,]\d+)?', text)
    numbers = [int(n.replace(',', '').replace('.', '').replace(' ', '')) for n in numbers if n.replace(',', '').replace('.', '').replace(' ', '').isdigit()]
    if not numbers:
        return None, None
    score = max(numbers)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    name = next((l[:30] for l in lines if len(l)>2 and not l.replace(' ',' , '').replace('.', '').replace(' ','').isdigit()), "Player")
    return score, name

async def update_leaderboard():
    global leaderboard_message
    channel_b = bot.get_channel(CHANNEL_B_ID)
    if not channel_b: return

    if not leaderboard:
        embed = discord.Embed(title="Leaderboard", description="No scores yet!", color=0x3498db)
    else:
        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Top 20 Leaderboard", color=0x00ff00)
        for rank, (uid, (score, url, name)) in enumerate(sorted_lb, 1):
            member = bot.get_user(uid)
            display = member.display_name if member else name
            embed.add_field(name=f"#{rank} — {score:,}", value=f"{display} [[image]]({url})", inline=False)
        embed.set_footer(text=f"{len(leaderboard)} total entries • Auto-updated")

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel_b.send(embed=embed)
    except:
        leaderboard_message = await channel_b.send(embed=embed)

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await update_leaderboard()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return

    for att in message.attachments:
        if att.filename.lower().endswith(('png','jpg','jpeg','webp')):
            try:
                data = await att.read()
                nparr = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                text = preprocess_image(img)
                score, name = extract_score_and_name(text)
                if not score or score < 100:
                    await message.add_reaction("❓")
                    continue

                old = leaderboard.get(message.author.id, (0,"",""))[0]
                if score > old:
                    leaderboard[message.author.id] = (score, att.url, message.author.display_name)
                    await message.add_reaction("⬆")
                else:
                    await message.add_reaction("✅")
                await update_leaderboard()
            except:
                await message.add_reaction("❌")

    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))   # ← token comes from environment / secrets
