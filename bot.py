# bot.py

import os
import re
import asyncio
import discord
from discord.ext import commands
import pytesseract
import cv2
from collections import defaultdict
from rapidfuzz import fuzz

TOKEN = os.getenv("DISCORD_TOKEN")
WATCH_CHANNEL_ID = 1441385260171661325
POST_CHANNEL_ID = 1441385329440460902
PLAYER_LOG_CHANNEL_ID = 1428423032929517669  # Replace with your log channel ID
ALLOWED_RESET_ROLES = ["R5", "R4"]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

leaderboard_memory = {}
last_leaderboard_msg = None

# ----------------------------

# OCR and Name Handling

# ----------------------------

def normalize_name(name: str) -> str:
return " ".join(name.strip().split())

def clean_ocr_name(name: str) -> str:
"""Fix common OCR misreads."""
name = normalize_name(name)
name = name.replace("|", "I").replace("0", "O").replace("1", "l")
name = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff\s-]", "", name)
return name

def extract_text_raw(path: str) -> str:
img = cv2.imread(path)
if img is None:
return ""
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
try:
text = pytesseract.image_to_string(gray, lang='chi_sim+eng')
except Exception:
text = pytesseract.image_to_string(gray)
return text or ""

def extract_leaderboard_from_image(path: str) -> dict:
"""Return dict of {player_name: damage} from screenshot."""
results = {}
img = cv2.imread(path)
if img is None:
return results

```
# Improved preprocessing
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
gray = cv2.medianBlur(gray, 3)
thresh = cv2.adaptiveThreshold(gray, 255,
                               cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 11, 2)
thresh = cv2.bitwise_not(thresh)
scale = 2
thresh = cv2.resize(thresh, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
cv2.imwrite("debug_thresh.png", thresh)  # optional for debugging

try:
    data = pytesseract.image_to_data(thresh,
                                     output_type=pytesseract.Output.DICT,
                                     lang='chi_sim+eng',
                                     config='--oem 3 --psm 6')
except Exception:
    data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)

lines = defaultdict(list)
n = len(data.get('text', []))
for i in range(n):
    text = (data['text'][i] or "").strip()
    conf_raw = data['conf'][i]
    try:
        conf = int(float(conf_raw))
    except Exception:
        conf = -1
    if not text or conf < 40:
        continue
    y = data['top'][i]
    left = data['left'][i]
    lines[y // 15].append((left, text))

sorted_lines = [sorted(words, key=lambda t: t[0]) for _, words in sorted(lines.items())]

prev_name = None
for words in sorted_lines:
    line_text = " ".join(w for _, w in words).strip()
    if not line_text:
        continue
    dp_match = re.search(r"Damage Points[:\s]*([\d\s,]+)", line_text, re.IGNORECASE)
    if dp_match and prev_name:
        damage_str = dp_match.group(1).replace(" ", "").replace(",", "")
        try:
            damage = int(damage_str)
            player = clean_ocr_name(prev_name)
            results[player] = damage
        except Exception:
            pass
        prev_name = None
    else:
        prev_name = line_text

return results
```

# ----------------------------

# Discord channel player name fetching

# ----------------------------

async def get_candidate_names(channel_id: int, limit: int = 50) -> list[str]:
"""Fetch last `limit` messages and extract potential player names."""
channel = bot.get_channel(channel_id)
if not channel:
return []
candidate_names = set()
async for msg in channel.history(limit=limit):
lines = msg.content.splitlines()
for line in lines:
clean_line = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', line).strip()
if len(clean_line) >= 2:
candidate_names.add(clean_line)
return list(candidate_names)

def match_official_name(ocr_name: str, candidates: list[str], threshold: int = 50) -> str:
"""Return best candidate name if match >= threshold, else original."""
best_name = ocr_name
highest_score = 0
ocr_name_clean = ocr_name.lower()
for cand in candidates:
try:
score = fuzz.ratio(ocr_name_clean, cand.lower())
except Exception:
score = 0
if score > highest_score and score >= threshold:
highest_score = score
best_name = cand
return best_name

# ----------------------------

# Merge leaderboard memory

# ----------------------------

def merge_with_memory(extracted: dict, candidates: list[str], threshold: int = 90):
global leaderboard_memory
for raw_name, dmg in extracted.items():
# Replace OCR name with official name if matched
official_name = match_official_name(raw_name, candidates, threshold=50)
new_name = normalize_name(official_name)
matched = False
if new_name in leaderboard_memory:
leaderboard_memory[new_name] = max(leaderboard_memory[new_name], dmg)
continue
for exist in list(leaderboard_memory.keys()):
try:
score = fuzz.ratio(new_name.lower(), exist.lower())
except Exception:
score = 0
if score >= threshold:
leaderboard_memory[exist] = max(leaderboard_memory[exist], dmg)
matched = True
break
if not matched:
leaderboard_memory[new_name] = dmg

# ----------------------------

# Format leaderboard

# ----------------------------

def format_leaderboard(result_dict: dict, add_emojis: bool = False, top_n: int = 50) -> str:
sorted_list = sorted(result_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
medals = ["🥇", "🥈", "🥉"]
number_emoji = {"0":"0️⃣","1":"1️⃣","2":"2️⃣","3":"3️⃣","4":"4️⃣",
"5":"5️⃣","6":"6️⃣","7":"7️⃣","8":"8️⃣","9":"9️⃣"}
lines = []
for idx, (name, dmg) in enumerate(sorted_list):
if add_emojis:
if idx < 3:
prefix = medals[idx]
else:
rank = str(idx + 1)
prefix = "".join(number_emoji.get(d, d) for d in rank)
lines.append(f"{prefix} {name} — {dmg}")
else:
lines.append(f"{name} — {dmg}")
return "\n".join(lines)

# ----------------------------

# Permissions

# ----------------------------

def can_reset(member: discord.Member) -> bool:
if member.guild_permissions.administrator:
return True
for role in member.roles:
if role.name in ALLOWED_RESET_ROLES:
return True
return False

# ----------------------------

# Commands

# ----------------------------

@bot.command(name="reset_leaderboard")
async def reset_leaderboard(ctx):
if not can_reset(ctx.author):
await ctx.send("❌ You do not have permission to reset the leaderboard.")
return
global leaderboard_memory, last_leaderboard_msg
leaderboard_memory = {}
last_leaderboard_msg = None
post_channel = bot.get_channel(POST_CHANNEL_ID)
if post_channel:
async for m in post_channel.history(limit=200):
if m.author == bot.user and "📊 OCR Leaderboard Results" in m.content:
try: await m.delete()
except Exception: pass
await post_channel.send("✅ Leaderboard has been reset.")

@bot.command(name="reset_memory")
async def reset_memory(ctx):
if not can_reset(ctx.author):
await ctx.send("❌ You do not have permission to reset memory.")
return
global leaderboard_memory
leaderboard_memory = {}
await ctx.send("✅ Leaderboard memory cleared.")

# ----------------------------

# Event: on_message

# ----------------------------

@bot.event
async def on_message(message: discord.Message):
global last_leaderboard_msg
await bot.process_commands(message)

```
if message.author == bot.user or message.channel.id != WATCH_CHANNEL_ID:
    return

image_att = next((att for att in message.attachments
                 if att.filename.lower().endswith((".png", ".jpg", ".jpeg"))), None)
if not image_att:
    return

temp_file = "latest.png"
try:
    await image_att.save(temp_file)

    raw_text = extract_text_raw(temp_file) or ""
    if "[" in raw_text or "]" in raw_text:
        try: await message.add_reaction("❌")
        except: pass
        warn = await message.channel.send(
            "❌ **Image invalid.** Please upload a screenshot from alliance mail and crop out everything except player names and damage values."
        )
        await asyncio.sleep(10)
        try: await warn.delete()
        except: pass
        return

    extracted = extract_leaderboard_from_image(temp_file)
    if not extracted:
        try: await message.add_reaction("❌")
        except: pass
        await message.channel.send("❌ OCR failed or no players detected.")
        return

    # Fetch candidate names from player log channel
    candidates = await get_candidate_names(PLAYER_LOG_CHANNEL_ID, limit=50)
    merge_with_memory(extracted, candidates)

    post_channel = bot.get_channel(POST_CHANNEL_ID)
    if not post_channel:
        return

    # Delete last leaderboard message
    if last_leaderboard_msg:
        try: await last_leaderboard_msg.delete()
        except: pass
        last_leaderboard_msg = None

    # Post leaderboard
    formatted_clean = format_leaderboard(leaderboard_memory, add_emojis=False, top_n=50)
    last_leaderboard_msg = await post_channel.send(f"**📊 OCR Leaderboard Results**\n{formatted_clean}")
    await asyncio.sleep(2)
    formatted_emojis = format_leaderboard(leaderboard_memory, add_emojis=True, top_n=50)
    try: await last_leaderboard_msg.edit(content=f"**📊 OCR Leaderboard Results**\n{formatted_emojis}")
    except: pass

finally:
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except: pass
```

# ----------------------------

# Run bot

# ----------------------------

if **name** == "**main**":
if not TOKEN:
raise RuntimeError("DISCORD_TOKEN environment variable required.")
bot.run(TOKEN)
