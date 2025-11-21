# bot.py
import os
import re
import json
import discord
from discord.ext import commands
import pytesseract
import cv2
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1441385260171661325  # channel to listen for screenshots
POST_CHANNEL_ID = 1441385329440460902   # channel to post leaderboard
LEADERBOARD_FILE = "leaderboard.json"
ALLOWED_RESET_ROLES = ["R5", "R4"]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load leaderboard if exists
if os.path.exists(LEADERBOARD_FILE):
    with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
        leaderboard = json.load(f)
else:
    leaderboard = {}

def save_leaderboard():
    with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

def extract_leaderboard_from_image(path):
    """
    OCR function to extract player names and their damage points.
    Expects each player as:
        Line 1: Player Name
        Line 2: Damage Points: XXXXXXX
    """
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)

    # Group text by Y-coordinate
    lines = defaultdict(list)
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        conf = int(data['conf'][i])
        if not text or conf < 40:
            continue
        y = data['top'][i]
        lines[y // 15].append((data['left'][i], text))

    # Sort lines top-to-bottom
    sorted_lines = [sorted(words, key=lambda t: t[0]) for _, words in sorted(lines.items())]

    results = {}
    prev_name = None
    for line in sorted_lines:
        line_text = " ".join(word for _, word in line).strip()
        match = re.search(r"Damage Points[:\s]*([\d\s,]+)", line_text, re.IGNORECASE)
        if match and prev_name:
            damage_str = match.group(1).replace(" ", "").replace(",", "")
            damage = int(damage_str)
            results[prev_name] = damage
            prev_name = None
        else:
            prev_name = line_text
    return results

def format_leaderboard(result_dict):
    """Format leaderboard with emojis for top 3, numbers for rest"""
    sorted_list = sorted(result_dict.items(), key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for idx, (name, dmg) in enumerate(sorted_list):
        prefix = medals[idx] if idx < 3 else f"{idx+1}."
        lines.append(f"{prefix} {name} — {dmg}")
    return "\n".join(lines)

def can_reset(member):
    """Check if a member can reset the leaderboard"""
    if member.guild_permissions.administrator:
        return True
    for role in member.roles:
        if role.name in ALLOWED_RESET_ROLES:
            return True
    return False

@bot.command(name="reset_leaderboard")
async def reset_leaderboard(ctx):
    if not can_reset(ctx.author):
        await ctx.send("❌ You do not have permission to reset the leaderboard.")
        return
    global leaderboard
    leaderboard = {}
    save_leaderboard()
    await ctx.send("✅ Leaderboard has been reset.")

@bot.event
async def on_message(message):
    await bot.process_commands(message)  # Ensure commands still work

    if message.channel.id != TARGET_CHANNEL_ID or message.author == bot.user:
        return

    for att in message.attachments:
        if att.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            temp_file = "latest.png"
            await att.save(temp_file)

            extracted = extract_leaderboard_from_image(temp_file)
            os.remove(temp_file)  # Clean up temp image

            if not extracted:
                await message.channel.send("❌ OCR failed or no players detected.")
                return

            # Update cumulative leaderboard
            for player, dmg in extracted.items():
                leaderboard[player] = max(leaderboard.get(player, 0), dmg)
            save_leaderboard()

            formatted = format_leaderboard(leaderboard)
            post_channel = bot.get_channel(POST_CHANNEL_ID)
            if post_channel:
                await post_channel.send(f"**📊 OCR Leaderboard Results**\n{formatted}")

bot.run(TOKEN)
