~~~{"variant":"standard","title":"Temporary Debug bot.py for OCR output","id":"93712"}
import os
import asyncio
import discord
from discord.ext import commands
import pytesseract
import cv2

TOKEN = os.getenv("DISCORD_TOKEN")
WATCH_CHANNEL_ID = 1441385260171661325

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    if message.author == bot.user or message.channel.id != WATCH_CHANNEL_ID:
        return
    image_att = next((att for att in message.attachments if att.filename.lower().endswith((".png",".jpg",".jpeg"))), None)
    if not image_att:
        return

    temp_file = "latest_debug.png"
    try:
        await image_att.save(temp_file)
        raw_text = extract_text_raw(temp_file) or ""
        print(f"RAW OCR OUTPUT:\n{raw_text}\n{'-'*50}")
        await message.channel.send(f"```RAW OCR OUTPUT:\n{raw_text}```")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable required.")
    bot.run(TOKEN)
~~~
