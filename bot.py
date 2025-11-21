# bot.py
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
