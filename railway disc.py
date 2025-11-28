# ================= REQUIRED INSTALLS =================
# requirements.txt should contain:
# discord.py
# unidecode

import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
import os
import time
from unidecode import unidecode

# ================= BOT SETUP =================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("TOKEN")  # Set in Railway environment variables

# ================= CONFIG =================

MAX_WARNINGS = 5
MUTE_DURATION = 300           # 5 minutes
BOT_DELETE_TIME = 5           # seconds bot messages stay visible
SPAM_MESSAGE_LIMIT = 5        # messages
SPAM_TIME_WINDOW = 7          # seconds

MOD_LOG_CHANNEL = "mod-logs"  # Name of the logging channel

user_warnings = {}
user_message_times = {}

# Pattern-based detection for slurs (safe)
SLUR_PATTERNS = [
    r"n+\W*[i1!]+\W*[gq9]+\W*[e3a]+\W*[r]+",
    r"f+\W*[a@4]+\W*[gq9]+\W*[o0]+\W*[t]+",
]

# ================= UTILITIES =================

def normalize(text):
    text = unidecode(text.lower())
    return re.sub(r'[^a-z0-9]', '', text)

def contains_slur(message):
    raw = message.content.lower()
    normalized = normalize(raw)
    for pattern in SLUR_PATTERNS:
        if re.search(pattern, raw) or re.search(pattern, normalized):
            return True
    return False

async def log_action(guild, content):
    """Send a log message to the MOD_LOG_CHANNEL."""
    for channel in guild.text_channels:
        if channel.name == MOD_LOG_CHANNEL:
            await channel.send(content)
            break

async def warn_user(member, channel, reason):
    user_id = member.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    warnings = user_warnings[user_id]

    msg = await channel.send(
        f"⚠️ {member.mention} {reason}\nWarning {warnings}/{MAX_WARNINGS}"
    )
    await asyncio.sleep(BOT_DELETE_TIME)
    await msg.delete()

    await log_action(member.guild, f"⚠️ {member} received a warning: {reason}. Total warnings: {warnings}")

    if warnings >= MAX_WARNINGS:
        user_warnings[user_id] = 0
        await mute_user(member, channel, reason="Reached max warnings")

async def mute_user(member, channel, reason="Violation"):
    MUTED_ROLE_NAME = "Muted"

    muted_role = discord.utils.get(member.guild.roles, name=MUTED_ROLE_NAME)
    if not muted_role:
        muted_role = await member.guild.create_role(name=MUTED_ROLE_NAME)
        for ch in member.guild.channels:
            await ch.set_permissions(muted_role, send_messages=False, speak=False)

    await member.add_roles(muted_role)

    notice = await channel.send(f"🔇 {member.mention} has been muted ({reason}).")
    await asyncio.sleep(BOT_DELETE_TIME)
    await notice.delete()

    await log_action(member.guild, f"🔇 {member} was muted. Reason: {reason}")

    await asyncio.sleep(MUTE_DURATION)
    await member.remove_roles(muted_role)
    await log_action(member.guild, f"🔊 {member} has been unmuted after mute duration.")

# ================= EVENTS =================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    author = message.author
    now = time.time()

    # ---------- ANTI-SPAM ----------
    times = user_message_times.get(author.id, [])
    times = [t for t in times if now - t < SPAM_TIME_WINDOW]
    times.append(now)
    user_message_times[author.id] = times

    if len(times) >= SPAM_MESSAGE_LIMIT:
        await message.delete()
        await warn_user(author, message.channel, "is spamming")
        await log_action(message.guild, f"⚠️ {author} triggered spam detection ({len(times)} messages in {SPAM_TIME_WINDOW}s)")
        return

    # ---------- SLUR FILTER ----------
    if contains_slur(message):
        await message.delete()
        await warn_user(author, message.channel, "used inappropriate language")
        return

    await bot.process_commands(message)

# ================= PERMISSION CHECK =================

def admin_only(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ================= SLASH COMMANDS =================

@bot.tree.command(name="warnings", description="Check a user's warnings")
async def warnings(interaction: discord.Interaction, user: discord.Member):
    count = user_warnings.get(user.id, 0)
    await interaction.response.send_message(
        f"⚠️ {user.mention} has {count}/{MAX_WARNINGS} warnings.",
        delete_after=BOT_DELETE_TIME
    )

@bot.tree.command(name="clearwarnings", description="Clear a user's warnings (Admin only)")
async def clearwarnings(interaction: discord.Interaction, user: discord.Member):
    if not admin_only(interaction):
        await interaction.response.send_message(
            "❌ You must be an administrator to use this command.",
            delete_after=BOT_DELETE_TIME
        )
        return

    user_warnings[user.id] = 0
    await interaction.response.send_message(
        f"✅ Warnings reset for {user.mention}.",
        delete_after=BOT_DELETE_TIME
    )
    await log_action(interaction.guild, f"✅ {interaction.user} reset warnings for {user}")

@bot.tree.command(name="mute", description="Mute a user (Admin only)")
async def mute(interaction: discord.Interaction, user: discord.Member):
    if not admin_only(interaction):
        await interaction.response.send_message(
            "❌ You must be an administrator to use this command.",
            delete_after=BOT_DELETE_TIME
        )
        return

    await mute_user(user, interaction.channel, reason="Admin mute")
    await interaction.response.send_message(
        f"🔇 {user.mention} has been muted by admin.",
        delete_after=BOT_DELETE_TIME
    )

@bot.tree.command(name="unmute", description="Unmute a user (Admin only)")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    if not admin_only(interaction):
        await interaction.response.send_message(
            "❌ You must be an administrator to use this command.",
            delete_after=BOT_DELETE_TIME
        )
        return

    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if muted_role:
        await user.remove_roles(muted_role)

    await interaction.response.send_message(
        f"🔊 {user.mention} has been unmuted by admin.",
        delete_after=BOT_DELETE_TIME
    )
    await log_action(interaction.guild, f"🔊 {user} was unmuted by {interaction.user}")

# ================= RUN BOT =================

bot.run(TOKEN)