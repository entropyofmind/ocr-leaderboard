# bot.py
import os
import re
import discord
from discord.ext import commands
import pytesseract
import cv2
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1441385260171661325  # channel to watch

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

def extract_leaderboard(path):
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

    # Collect text by Y-coordinate lines
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
        # Detect damage line
        match = re.search(r"Damage Points[:\s]*([\d]+)", line_text, re.IGNORECASE)
        if match and prev_name:
            damage = int(match.group(1))
            # Merge duplicates, keep highest damage
            results[prev_name] = max(results.get(prev_name, 0), damage)
            prev_name = None  # reset for next player
        else:
            # Assume this line is a player name
            prev_name = line_text

    # Sort descending by damage
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    return sorted_results

def format_leaderboard(result_list):
    """Formats the leaderboard with emojis for top 3 and numbers for the rest."""
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for idx, (name, dmg) in enumerate(result_list):
        prefix = medals[idx] if idx < 3 else f"{idx+1}."
        lines.append(f"{prefix} {name} — {dmg}")
    return "\n".join(lines)

@bot.event
async def on_message(message):
    # Ignore messages from other channels or from the bot itself
    if message.channel.id != TARGET_CHANNEL_ID or message.author == bot.user:
        return

    # Process attachments
    for att in message.attachments:
        if att.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            fp = "latest.png"
            await att.save(fp)

            # Extract leaderboard
            results = extract_leaderboard(fp)
            if not results:
                await message.channel.send("❌ OCR failed or no players detected.")
                return

            leaderboard_text = format_leaderboard(results)
            await message.channel.send(f"**📊 OCR Leaderboard Results**\n{leaderboard_text}")

bot.run(TOKEN)
