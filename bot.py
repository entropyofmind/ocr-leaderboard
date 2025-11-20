import discord
from discord.ext import commands
import pytesseract
import cv2
import numpy as np
import re
import asyncio
import os

# ================== YOUR CHANNELS ==================
CHANNEL_A_ID = 1428424023435513876   # Screenshots channel
CHANNEL_B_ID = 1428424076162240702   # Leaderboard channel
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

leaderboard = {}          # {user_id: (best_score, image_url, display_name)}
leaderboard_message = None

def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    candidates = [
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2),
        cv2.threshold(cv2.bitwise_not(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    ]
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
    if score < 100:
        return None, None

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    name = next((l[:30] for l in lines if len(l) > 2 and not str(score) in l and not l.replace(' ', '').replace('.', '').replace(',', '').isdigit()), None)
    return score, name or "Unknown Player"

async def update_leaderboard():
    global leaderboard_message
    channel_b = bot.get_channel(CHANNEL_B_ID)
    if not channel_b:
        return

    if not leaderboard:
        embed = discord.Embed(
            title="Top 20 Leaderboard",
            description="No scores yet — post a screenshot in the other channel!",
            color=0x2f3136
        )
    else:
        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1][0], reverse=True)[:20]
        embed = discord.Embed(title="Top 20 Leaderboard", color=0x00ff00)
        for rank, (uid, (score, url, name)) in enumerate(sorted_lb, 1):
            member = bot.get_user(uid)
            display_name = member.display_name if member else name
            medal = "crown" if rank == 1 else "2nd_place_medal" if rank == 2 else "3rd_place_medal" if rank == 3 else f"#{rank}"
            embed.add_field(
                name=f"{medal} **{score:,}**",
                value=f"[{display_name}]({url})",
                inline=False
            )
        embed.set_footer(text=f"{len(leaderboard)} total entries • Auto-updated")
        embed.timestamp = discord.utils.utcnow()

    try:
        if leaderboard_message:
            await leaderboard_message.edit(embed=embed)
        else:
            leaderboard_message = await channel_b.send(embed=embed)
            await leaderboard_message.pin()
            async for msg in channel_b.history(limit=1):
                if msg.type == discord.MessageType.pins_add:
                    await msg.delete()
    except Exception as e:
        print(f"Leaderboard update error: {e}")
        leaderboard_message = await channel_b.send(embed=embed)
        await leaderboard_message.pin()

@bot.event
async def on_ready():
    print(f"{bot.user} is online and scanning screenshots!")
    await update_leaderboard()

@bot.event
async def on_message(message):
    if message.channel.id != CHANNEL_A_ID or not message.attachments:
        return

    for att in message.attachments:
        if att.filename.lower().endswith(('png', 'jpg', 'jpeg', 'webp')):
            try:
                data = await att.read()
                nparr = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    await message.add_reaction("error")
                    continue

                text = preprocess_image(img)
                score, name = extract_score_and_name(text)

                if not score:
                    await message.add_reaction("question")
                    continue

                old_score = leaderboard.get(message.author.id, (0, "", ""))[0]
                if score > old_score:
                    leaderboard[message.author.id] = (score, att.url, message.author.display_name)
                    await message.add_reaction("chart_with_upwards_trend")
                else:
                    await message.add_reaction("white_check_mark")

                await update_leaderboard()

            except Exception as e:
                print(f"Processing error: {e}")
                await message.add_reaction("cross_mark")

    await bot.process_commands(message)

@bot.command()
@commands.has_permissions(administrator=True)
async def refresh(ctx):
    await update_leaderboard()
    await ctx.send("Leaderboard refreshed!", delete_after=3)

bot.run(os.getenv("DISCORD_TOKEN"))
