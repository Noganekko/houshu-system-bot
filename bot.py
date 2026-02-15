import discord
from discord import app_commands
import sqlite3
import datetime
import os
from flask import Flask

# =========================
# 環境変数
# =========================
TOKEN = os.getenv("TOKEN")  # Renderで設定済み

# =========================
# Discord セットアップ
# =========================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# Flask サーバー（Render用）
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Houshu System Bot is running!"

# =========================
# データベース初期化
# =========================
DB_NAME = "houshu.db"
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

# ユーザー情報
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    missed_count INTEGER DEFAULT 0,
    exempt INTEGER DEFAULT 0
)
""")

# ポイント情報
c.execute("""
CREATE TABLE IF NOT EXISTS points (
    user_id TEXT PRIMARY KEY,
    eval_pt INTEGER DEFAULT 0,
    carry_pt INTEGER DEFAULT 0,
    save_pt INTEGER DEFAULT 0
)
""")

# 制作報告
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
    # 管理者チェック
    if "管理" not in [role.name for role in interaction.user.roles]:
        await interaction.response.send_message("管理者専用コマンドです")
        return

    c.execute("SELECT user_id, pt, status FROM reports WHERE id=?", (report_id,))
    data = c.fetchone()
    if not data:
        await interaction.response.send_message("報告が存在しません")
        return
    user_id, pt, status = data
    if status != "pending":
        await interaction.response.send_message("既に処理済みです")
        return

    c.execute("UPDATE reports SET status='approved' WHERE id=?", (report_id,))
    c.execute("INSERT OR IGNORE INTO points (user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE points SET eval_pt = eval_pt + ? WHERE user_id=?", (pt, user_id))
    conn.commit()
    await interaction.response.send_message("承認しました")

# =========================
# 却下コマンド
# =========================
@tree.command(name="reject", description="報告を却下")
async def reject(interaction: discord.Interaction, report_id: int):
    if "管理" not in [role.name for role in interaction.user.roles]:
        await interaction.response.send_message("管理者専用コマンドです")
        return
    c.execute("SELECT status FROM reports WHERE id=?", (report_id,))
    data = c.fetchone()
    if not data:
        await interaction.response.send_message("報告が存在しません")
        return
    if data[0] != "pending":
        await interaction.response.send_message("既に処理済みです")
        return
    c.execute("UPDATE reports SET status='rejected' WHERE id=?", (report_id,))
    conn.commit()
    await interaction.response.send_message("却下しました")

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

# =========================
# 月次決算コマンド（管理者専用）
# =========================
@tree.command(name="monthly_close", description="月次決算を実行")
async def monthly_close(interaction: discord.Interaction):
    if "管理" not in [role.name for role in interaction.user.roles]:
        await interaction.response.send_message("管理者専用コマンドです")
        return

    month = datetime.datetime.now().strftime("%Y-%m")

    c.execute("SELECT user_id, eval_pt, carry_pt, save_pt FROM points")
    all_users = c.fetchall()

    for user_id, eval_pt, carry_pt, save_pt in all_users:
        # ノルマ達成判定（20Pt）
        used_eval = min(eval_pt + carry_pt, 20)
        remaining = (eval_pt + carry_pt) - used_eval

        # 未達カウント更新
        c.execute("SELECT missed_count, exempt FROM users WHERE user_id=?", (user_id,))
        data = c.fetchone()
        if data:
            missed_count, exempt = data
        else:
            missed_count, exempt = 0, 0
            c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))

        if exempt == 0:
            if used_eval < 20:
                missed_count += 1
            else:
                missed_count = 0

        # ポイント処理
        carry_pt = remaining  # 繰越Pt
        save_pt += max(eval_pt + carry_pt - 20, 0)  # 貯蓄Pt加算

        c.execute("UPDATE points SET eval_pt=0, carry_pt=?, save_pt=? WHERE user_id=?",
                  (carry_pt, save_pt, user_id))
        c.execute("UPDATE users SET missed_count=? WHERE user_id=?", (missed_count, user_id))

    conn.commit()
    await interaction.response.send_message("月次決算を実行しました")

# =========================
# Bot起動
# =========================
if __name__ == "__main__":
    from threading import Thread
    def run_flask():
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

    Thread(target=run_flask).start()
    client.run(TOKEN)
