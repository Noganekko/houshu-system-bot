import discord
from discord import app_commands
import sqlite3
import datetime
import os

TOKEN = os.getenv("TOKEN")  # Render用

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# データベース初期化
# =========================

conn = sqlite3.connect("houshu.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    missed_count INTEGER DEFAULT 0,
    exempt INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS points (
    user_id TEXT PRIMARY KEY,
    eval_pt INTEGER DEFAULT 0,
    carry_pt INTEGER DEFAULT 0,
    save_pt INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    pt INTEGER,
    status TEXT,
    month TEXT
)
""")

conn.commit()

# =========================
# 起動時処理
# =========================

@client.event
async def on_ready():
    await tree.sync()
    print("Houshu System Bot 起動")

# =========================
# 制作報告コマンド
# =========================

@tree.command(name="report", description="制作報告を提出")
async def report(interaction: discord.Interaction, pt: int):
    user_id = str(interaction.user.id)
    month = datetime.datetime.now().strftime("%Y-%m")

    c.execute("INSERT INTO reports (user_id, pt, status, month) VALUES (?, ?, ?, ?)",
              (user_id, pt, "pending", month))
    conn.commit()

    await interaction.response.send_message("報告を受理しました（pending）")

# =========================
# 承認コマンド
# =========================

@tree.command(name="approve", description="報告を承認")
async def approve(interaction: discord.Interaction, report_id: int):

    c.execute("SELECT user_id, pt, status FROM reports WHERE id=?", (report_id,))
    data = c.fetchone()

    if not data:
        await interaction.response.send_message("報告が存在しません")
        return

    user_id, pt, status = data

    if status != "pending":
        await interaction.response.send_message("既に処理済みです")
        return

    # 承認処理
    c.execute("UPDATE reports SET status='approved' WHERE id=?", (report_id,))

    # ポイント加算
    c.execute("INSERT OR IGNORE INTO points (user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE points SET eval_pt = eval_pt + ? WHERE user_id=?", (pt, user_id))

    conn.commit()

    await interaction.response.send_message("承認しました")

# =========================
# 自分のポイント確認
# =========================

@tree.command(name="mypoint", description="自分のポイント確認")
async def mypoint(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    c.execute("SELECT eval_pt, carry_pt, save_pt FROM points WHERE user_id=?", (user_id,))
    data = c.fetchone()

    if not data:
        await interaction.response.send_message("ポイント記録なし")
        return

    eval_pt, carry_pt, save_pt = data

    await interaction.response.send_message(
        f"評価Pt: {eval_pt}\n繰越Pt: {carry_pt}\n貯蓄Pt: {save_pt}"
    )

client.run(TOKEN)
