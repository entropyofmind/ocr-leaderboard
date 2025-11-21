# bot.py
import os
import re
import discord
from discord.ext import commands
import pytesseract
import cv2
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")
WATCH_CHANNEL_ID = 1441385260171661325  # channel to watch for screenshots
POST_CHANNEL_ID = 1441385329440460902   # channel to post leaderboard
ALLOWED_RESET_ROLES = ["R5", "R4"]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def normalize_name(name):
    """Normalize player names to prevent duplicates"""
    return " ".join(name.strip().split())

def extract_leaderboard_from_image(path):
    """
    OCR function to extract player names and damage points.
    Handles Unicode names including Chinese characters and parentheses.
    """
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # OCR with Unicode support
    data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT, lang='chi_sim+eng')

    lines = defaultdict(list)
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        conf = int(data['conf'][i])
        if not text or conf < 40:
            continue
        y = data['top'][i]
        lines[y // 15].append((data['left'][i], text))

    sorted_lines = [sorted(words, key=lambda t: t[0]) for _, words in sorted(lines.items())]

    results = {}
    prev_name = None
    for line in sorted_lines:
        line_text = " ".join(word for _, word in line).strip()
        match = re.search(r"Damage Points[:\s]*([\d\s,]+)", line_text, re.IGNORECASE)
        if match and prev_name:
            damage_str = match.group(1).replace(" ", "").replace(",", "")
            try:
                damage = int(damage_str)
                player = normalize_name(prev_name)
                results[player] = damage
            except ValueError:
                pass
            prev_name = None
        else:
            prev_name = line_text
    return results

def format_leaderboard(result_dict):
    """Format leaderboard with emojis for top 3, numbers for the rest"""
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

def parse_leaderboard_message(msg_content):
    """Parse a previous leaderboard message into {player: damage}"""
    leaderboard_dict = {}
    lines = msg_content.splitlines()[1:]  # skip header
    for line in lines:
        line = line.strip()
        if not line or "—" not in line:
            continue
        # Remove emoji or number prefix
        line = re.sub(r"^[^\w\d]*", "", line)
        # Split by last '—' to keep names with dashes intact
        parts = line.rsplit("—", 1)
        if len(parts) != 2:
            continue
        name, dmg = parts
        name = normalize_name(name)
        try:
            dmg = int(re.sub(r"[^\d]", "", dmg.strip()))
            leaderboard_dict[name] = dmg
        except ValueError:
            continue
    return leaderboard_dict

async def read_latest_leaderboard():
    """Read the latest leaderboard message from POST_CHANNEL_ID"""
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if not post_channel:
        return {}
    async for msg in post_channel.history(limit=50):
        if msg.author == bot.user and "📊 OCR Leaderboard Results" in msg.content:
            return parse_leaderboard_message(msg.content)
    return {}

@bot.command(name="reset_leaderboard")
async def reset_leaderboard(ctx):
    if not can_reset(ctx.author):
        await ctx.send("❌ You do not have permission to reset the leaderboard.")
        return
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if post_channel:
        # Delete previous leaderboard messages
        async for msg in post_channel.history(limit=50):
            if msg.author == bot.user and "📊 OCR Leaderboard Results" in msg.content:
                await msg.delete()
        await post_channel.send("✅ Leaderboard has been reset.")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != WATCH_CHANNEL_ID or message.author == bot.user:
        return

    for att in message.attachments:
        if att.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            temp_file = "latest.png"
            await att.save(temp_file)

            extracted = extract_leaderboard_from_image(temp_file)
            os.remove(temp_file)

            if not extracted:
                await message.channel.send("❌ OCR failed or no players detected.")
                return

            # Read the most recent leaderboard
            current_leaderboard = await read_latest_leaderboard()

            # Merge extracted with existing leaderboard, keep highest damage
            for player, dmg in extracted.items():
                player = normalize_name(player)
                current_leaderboard[player] = max(current_leaderboard.get(player, 0), dmg)

            # Post updated leaderboard
            formatted = format_leaderboard(current_leaderboard)
            post_channel = bot.get_channel(POST_CHANNEL_ID)
            if post_channel:
                await post_channel.send(f"**📊 OCR Leaderboard Results**\n{formatted}")

bot.run(TOKEN)
