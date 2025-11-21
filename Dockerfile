# Updated Project Files

Below are the fully rewritten versions of your files reflecting:

* Correct OCR extraction (Unicode-friendly, numeric-safe parsing)
* Sorted leaderboard
* Duplicate merging
* Only processing the latest screenshot
* Fixed emojis
* Cleaned Dockerfile
* Cleaned requirements.txt

---

## **bot.py**

```python
# bot.py
import os
import discord
from discord.ext import commands
import pytesseract
import cv2
import re
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# OCR extraction function

def extract_leaderboard(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)

    rows = defaultdict(list)
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if not text:
            continue
        conf = int(data['conf'][i])
        if conf < 40:
            continue

        x = data['left'][i]
        y = data['top'][i]
        row_key = y // 15
        rows[row_key].append((x, text))

    results = {}

    for row in rows.values():
        row_sorted = sorted(row, key=lambda t: t[0])
        words = [w for _, w in row_sorted]

        damage = None
        for w in reversed(words):
            if re.fullmatch(r"\d+", w):
                damage = int(w)
                break

        if damage is None:
            continue

        name_words = words[:words.index(str(damage))]
        name = " ".join(name_words).strip()
        if not name:
            continue

        results[name] = max(results.get(name, 0), damage)

    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


# Helper: format leaderboard

def format_leaderboard(result_list):
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for idx, (name, dmg) in enumerate(result_list):
        prefix = medals[idx] if idx < 3 else f"{idx+1}."
        lines.append(f"{prefix} {name} — {dmg}")
    return "\n".join(lines)


# Command: analyze last screenshot

@bot.command(name="ocr")
async def ocr_latest(ctx):
    channel = ctx.channel
    last_img = None

    async for msg in channel.history(limit=50):
        if msg.attachments:
            for att in msg.attachments:
                if any(att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
                    last_img = att
                    break
        if last_img:
            break

    if not last_img:
        await ctx.send("❌ No recent screenshot found in the last 50 messages.")
        return

    fp = "latest.png"
    await last_img.save(fp)

    results = extract_leaderboard(fp)
    if not results:
        await ctx.send("❌ OCR failed or no players detected.")
        return

    text = format_leaderboard(results)
    await ctx.send(f"**📊 OCR Leaderboard Results**\n{text}")


bot.run(TOKEN)
```

---

## **Dockerfile**

```Dockerfile
FROM python:3.10-slim

# Install dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr libtesseract-dev && \
    apt-get clean

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
```

---

## **requirements.txt**

```txt
discord.py
pytesseract
opencv-python-headless
```
