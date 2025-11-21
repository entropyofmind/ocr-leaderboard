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

# ------------------- Utilities -------------------

def normalize_name(name):
    """Normalize player names to prevent duplicates."""
    # Strip leading/trailing whitespace, replace multiple spaces with single
    name = " ".join(name.strip().split())
    # Remove any leading digits/punctuation/number emojis
    name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", name)
    return name

def remove_emojis(text):
    """Remove all emojis from text."""
    # Pattern to remove most emojis
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols & Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols, Symbols & Pictographs Extended-A
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u26FF\u2700-\u27BF"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

# ------------------- OCR -------------------

def extract_leaderboard_from_image(path):
    """Extract player names and damage points from image using OCR."""
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

# ------------------- Leaderboard Parsing -------------------

def parse_leaderboard_message(msg_content):
    """Parse previous leaderboard into {player: damage}."""
    leaderboard_dict = {}
    lines = msg_content.splitlines()[1:]  # skip header
    for line in lines:
        line = line.strip()
        if not line or "—" not in line:
            continue
        line = remove_emojis(line)  # remove all emojis
        line = re.sub(r"^[^\w\u4e00-\u9fff\d]+", "", line)  # strip remaining non-name chars
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

# ------------------- Formatting -------------------

def format_leaderboard(result_dict, top_n=50):
    """Format leaderboard with medals for top 3, number emojis for 4–50."""
    sorted_list = sorted(result_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
    medals = ["🥇", "🥈", "🥉"]
    number_emoji = {
        "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
        "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"
    }
    lines = []
    for idx, (name, dmg) in enumerate(sorted_list):
        if idx < 3:
            prefix = medals[idx]
        else:
            rank = str(idx + 1)
            prefix = "".join(number_emoji[d] for d in rank)
        lines.append(f"{prefix} {name} — {dmg}")
    return "\n".join(lines)

# ------------------- Permissions -------------------

def can_reset(member):
    """Check if a member can reset leaderboard."""
    if member.guild_permissions.administrator:
        return True
    for role in member.roles:
        if role.name in ALLOWED_RESET_ROLES:
            return True
    return False

# ------------------- Bot Functions -------------------

async def get_latest_leaderboard_message():
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if not post_channel:
        return None, {}
    async for msg in post_channel.history(limit=100):
        if msg.author == bot.user and "📊 OCR Leaderboard Results" in msg.content:
            return msg, parse_leaderboard_message(msg.content)
    return None, {}

@bot.command(name="reset_leaderboard")
async def reset_leaderboard(ctx):
    if not can_reset(ctx.author):
        await ctx.send("❌ You do not have permission to reset the leaderboard.")
        return
    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if post_channel:
        msg, _ = await get_latest_leaderboard_message()
        if msg:
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

            # Get latest leaderboard
            latest_msg, current_leaderboard = await get_latest_leaderboard_message()

            # Merge extracted data with old leaderboard (normalized names)
            for player, dmg in extracted.items():
                player = normalize_name(player)
                current_leaderboard[player] = max(current_leaderboard.get(player, 0), dmg)

            formatted = format_leaderboard(current_leaderboard, top_n=50)

            post_channel = bot.get_channel(POST_CHANNEL_ID)
            if post_channel:
                if latest_msg:
                    await latest_msg.edit(content=f"**📊 OCR Leaderboard Results**\n{formatted}")
                else:
                    await post_channel.send(f"**📊 OCR Leaderboard Results**\n{formatted}")

bot.run(TOKEN)
