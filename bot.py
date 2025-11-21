# bot.py
import os
import re
import discord
from discord.ext import commands
import pytesseract
import cv2
from collections import defaultdict
import asyncio
from rapidfuzz import fuzz

TOKEN = os.getenv("DISCORD_TOKEN")
WATCH_CHANNEL_ID = 1441385260171661325
POST_CHANNEL_ID = 1441385329440460902
ALLOWED_RESET_ROLES = ["R5", "R4"]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------- Memory -------------------
leaderboard_memory = {}  # player_name -> damage

# ------------------- Utilities -------------------

def normalize_name(name):
    name = " ".join(name.strip().split())
    name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", name)
    return name

def remove_emojis(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u26FF\u2700-\u27BF"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

# ------------------- OCR -------------------

def extract_leaderboard_from_image(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

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

# ------------------- Fuzzy Merge -------------------

def merge_with_memory(extracted):
    global leaderboard_memory
    for new_player, new_dmg in extracted.items():
        new_player = normalize_name(new_player)
        matched = False
        for existing_player in leaderboard_memory:
            ratio = fuzz.ratio(new_player.lower(), existing_player.lower())
            if ratio >= 90:  # adjust threshold if needed
                leaderboard_memory[existing_player] = max(leaderboard_memory[existing_player], new_dmg)
                matched = True
                break
        if not matched:
            leaderboard_memory[new_player] = new_dmg

# ------------------- Formatting -------------------

def format_leaderboard(result_dict, add_emojis=False, top_n=50):
    sorted_list = sorted(result_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
    medals = ["🥇", "🥈", "🥉"]
    number_emoji = {
        "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
        "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"
    }
    lines = []
    for idx, (name, dmg) in enumerate(sorted_list):
        if add_emojis:
            if idx < 3:
                prefix = medals[idx]
            else:
                rank = str(idx + 1)
                prefix = "".join(number_emoji[d] for d in rank)
            lines.append(f"{prefix} {name} — {dmg}")
        else:
            lines.append(f"{name} — {dmg}")
    return "\n".join(lines)

# ------------------- Permissions -------------------

def can_reset(member):
    if member.guild_permissions.administrator:
        return True
    for role in member.roles:
        if role.name in ALLOWED_RESET_ROLES:
            return True
    return False

# ------------------- Bot Commands -------------------

@bot.command(name="reset_leaderboard")
async def reset_leaderboard(ctx):
    if not can_reset(ctx.author):
        await ctx.send("❌ You do not have permission to reset the leaderboard.")
        return
    global leaderboard_memory
    leaderboard_memory = {}
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if post_channel:
        async for msg in post_channel.history(limit=100):
            if msg.author == bot.user and "📊 OCR Leaderboard Results" in msg.content:
                await msg.delete()
        await post_channel.send("✅ Leaderboard has been reset.")

# ------------------- Bot Event -------------------

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != WATCH_CHANNEL_ID or message.author == bot.user:
        return

    # Process only the first valid image attachment
    image_att = next(
        (att for att in message.attachments if att.filename.lower().endswith((".png", ".jpg", ".jpeg"))),
        None
    )
    if not image_att:
        return

    temp_file = "latest.png"
    await image_att.save(temp_file)
    extracted = extract_leaderboard_from_image(temp_file)
    os.remove(temp_file)

    if not extracted:
        await message.channel.send("❌ OCR failed or no players detected.")
        return

    # Merge new screenshot into memory with fuzzy matching
    merge_with_memory(extracted)

    # Post clean leaderboard (no emojis)
    formatted_clean = format_leaderboard(leaderboard_memory, add_emojis=False)
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if not post_channel:
        return

    msg = await post_channel.send(f"**📊 OCR Leaderboard Results**\n{formatted_clean}")

    # Wait 2 seconds, then edit to add emojis
    await asyncio.sleep(2)
    formatted_emojis = format_leaderboard(leaderboard_memory, add_emojis=True)
    await msg.edit(content=f"**📊 OCR Leaderboard Results**\n{formatted_emojis}")

bot.run(TOKEN)
