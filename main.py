import discord
from discord.ext import commands, tasks
from flask import Flask
import os
import asyncio
import threading
import re
import unicodedata
import aiohttp

from datetime import datetime, timedelta, UTC
from discord.utils import utcnow

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.environ.get("DISCORD")

ALLOWED_CHANNEL_ID = 1403040565137899733

SELF_PING_URL = "https://sevenmaya-bot.onrender.com"

TIMEOUT_DURATION = timedelta(hours=1)

WARNING_COOLDOWN = timedelta(hours=1)

if not TOKEN:
    raise ValueError("Missing DISCORD token")

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

@app.route("/health")
def health():

    return {
        "status": "online",
        "guilds": len(bot.guilds) if "bot" in globals() else 0
    }

def run_flask():

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )

# =========================================================
# BOT
# =========================================================

class MyBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        self.last_link_time = {}

        self.REPLACEMENTS = {

            "@": "a",
            "4": "a",
            "à": "a",
            "á": "a",
            "â": "a",
            "ä": "a",
            "å": "a",

            "8": "b",
            "ß": "b",

            "(": "c",
            "¢": "c",
            "©": "c",
            "ç": "c",

            "3": "e",
            "€": "e",
            "&": "e",
            "ë": "e",
            "è": "e",
            "é": "e",
            "ê": "e",

            "6": "g",
            "9": "g",

            "#": "h",

            "!": "i",
            "1": "i",
            "¡": "i",
            "|": "i",
            "í": "i",
            "î": "i",
            "ï": "i",
            "ì": "i",

            "£": "l",
            "¬": "l",

            "0": "o",
            "ò": "o",
            "ó": "o",
            "ô": "o",
            "ö": "o",
            "ø": "o",

            "$": "s",
            "5": "s",
            "§": "s",
            "š": "s",

            "7": "t",
            "+": "t",
            "†": "t",

            "2": "z",

            "¥": "y",

            "*": "",
            "^": "",
            "~": "",
            "`": "",
            "?": "",
            ",": "",
            "_": "",
            ";": "",
            "'": "",
            "\"": "",
            "\\": "",
            "=": "",
            "%": ""
        }

        self.LINK_REGEX = re.compile(
            r"(https?:\/\/|www\.|discord\.gg\/|discord\.com\/invite\/|"
            r"[a-zA-Z0-9-]+\.(com|net|org|gg|io|me|co|xyz|info|app|site|store|online|tech|dev|link|ru|tk))",
            re.IGNORECASE
        )

        self.SHORTENERS = [

            "bit.ly",
            "tinyurl.com",
            "t.co",
            "goo.gl",
            "is.gd",
            "cutt.ly",
            "rebrand.ly",
            "shorturl.at",
            "tiny.one"
        ]

        self.SPOTIFY_WHITELIST = [

            "spotify.com",
            "open.spotify.com",
            "spotify.link"
        ]

    # =========================================================
    # SETUP
    # =========================================================

    async def setup_hook(self):

        self.update_status.start()
        self.self_ping.start()
        self.cleanup_cache.start()

    async def on_ready(self):

        print("=" * 50)
        print(f"Logged as : {self.user}")
        print(f"Bot ID    : {self.user.id}")
        print(f"Guilds    : {len(self.guilds)}")
        print("=" * 50)

    # =========================================================
    # STATUS
    # =========================================================

    @tasks.loop(minutes=10)
    async def update_status(self):

        try:

            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers"
            )

            await self.change_presence(
                status=discord.Status.online,
                activity=activity
            )

        except Exception as e:
            print("Status Error:", e)

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()

    # =========================================================
    # SELF PING
    # =========================================================

    @tasks.loop(minutes=5)
    async def self_ping(self):

        try:

            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.get(
                    SELF_PING_URL
                ) as response:

                    print(f"[SELF PING] {response.status}")

        except Exception as e:
            print("Self Ping Error:", e)

    @self_ping.before_loop
    async def before_self_ping(self):
        await self.wait_until_ready()

    # =========================================================
    # CLEAN CACHE
    # =========================================================

    @tasks.loop(hours=6)
    async def cleanup_cache(self):

        try:

            now = datetime.now(UTC)

            self.last_link_time = {
                k: v
                for k, v in self.last_link_time.items()
                if (now - v) < timedelta(days=1)
            }

            print("Cache cleaned")

        except Exception as e:
            print("Cache Cleanup Error:", e)

    @cleanup_cache.before_loop
    async def before_cleanup(self):
        await self.wait_until_ready()

    # =========================================================
    # NORMALIZE TEXT
    # =========================================================

    def normalize_text(self, text: str) -> str:

        if not text:
            return ""

        text = text.lower()

        text = re.sub(
            r"[\u200B-\u200D\uFEFF]",
            "",
            text
        )

        for old, new in self.REPLACEMENTS.items():
            text = text.replace(old, new)

        text = unicodedata.normalize(
            "NFKD",
            text
        )

        text = ''.join(
            c for c in text
            if not unicodedata.combining(c)
        )

        text = text.replace("ـ", "")

        text = re.sub(
            r"(.)\1{2,}",
            r"\1",
            text
        )

        text = re.sub(
            r"[^a-z0-9\u0621-\u064A\s]+",
            "",
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        return text

    # =========================================================
    # LINK DETECTION
    # =========================================================

    def contains_link(
        self,
        message: discord.Message
    ) -> bool:

        full_content = message.content or ""

        for embed in message.embeds:

            if embed.url:
                full_content += f" {embed.url}"

            if embed.title:
                full_content += f" {embed.title}"

            if embed.description:
                full_content += f" {embed.description}"

        raw = full_content.lower()

        normalized = self.normalize_text(
            full_content
        ).replace(" ", "")

        # Spotify whitelist
        for domain in self.SPOTIFY_WHITELIST:

            if domain in raw:
                return False

        # Markdown links
        markdown_links = re.findall(
            r"\[.*?\]\((.*?)\)",
            raw
        )

        for link in markdown_links:

            if not any(
                domain in link
                for domain in self.SPOTIFY_WHITELIST
            ):
                return True

        # Regex links
        if self.LINK_REGEX.search(raw):
            return True

        # Hidden links
        suspicious = [

            "http",
            "https",
            "www",
            "discordgg",
            "discordcominvite"
        ]

        for item in suspicious:

            if item in normalized:
                return True

        # Shorteners
        for shortener in self.SHORTENERS:

            if shortener in raw:
                return True

        # Attachments
        for attachment in message.attachments:

            filename = attachment.filename.lower()

            if re.search(
                r"\.(com|net|org|gg|io|xyz|ru|tk)",
                filename
            ):
                return True

        return False

    # =========================================================
    # WARNING
    # =========================================================

    async def send_warning(
        self,
        channel,
        title,
        description,
        color
    ):

        try:

            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=utcnow()
            )

            await channel.send(
                embed=embed,
                delete_after=10
            )

        except Exception as e:
            print("Warning Error:", e)

    # =========================================================
    # AUTO TIMEOUT
    # =========================================================

    async def apply_timeout(
        self,
        member: discord.Member,
        reason: str
    ) -> bool:

        try:

            if member.guild.owner_id == member.id:
                return False

            if member.top_role >= member.guild.me.top_role:
                return False

            until = utcnow() + TIMEOUT_DURATION

            await member.timeout(
                until,
                reason=reason
            )

            return True

        except Exception as e:

            print("Timeout Error:", e)
            return False

    # =========================================================
    # MESSAGE EVENT
    # =========================================================

    async def on_message(
        self,
        message: discord.Message
    ):

        if message.author.bot:
            return

        if not message.guild:
            return

        user_id = message.author.id

        now = datetime.now(UTC)

        # =====================================================
        # IGNORE STAFF / ADMINS / MUTE USERS
        # =====================================================

        if (

            message.author.guild_permissions.manage_messages
            or message.author.guild_permissions.administrator
            or user_id in ALLOWED_MUTE_USERS

        ):

            await self.process_commands(message)
            return

        # =====================================================
        # LINK PROTECTION
        # =====================================================

        if self.contains_link(message):

            # Allowed room
            if message.channel.id == ALLOWED_CHANNEL_ID:

                try:
                    await asyncio.sleep(5)
                    await message.delete()
                except:
                    pass

                return

            # Delete message
            try:
                await message.delete()
            except:
                pass

            last_time = self.last_link_time.get(user_id)

            # First warning
            if (
                not last_time or
                (now - last_time) > WARNING_COOLDOWN
            ):

                self.last_link_time[user_id] = now

                await self.send_warning(

                    message.channel,

                    "⚠️ تحذير من الروابط",

                    f"{message.author.mention} نشر الروابط ممنوع. المرة القادمة سيتم اسكاتك.",

                    0xFFFF00
                )

            # Timeout
            else:

                success = await self.apply_timeout(

                    message.author,
                    "نشر روابط"

                )

                if success:

                    await self.send_warning(

                        message.channel,

                        "⛔ تم اسكاتك",

                        f"{message.author.mention} تم اسكاتك بسبب تكرار نشر الروابط.",

                        0xFF0000
                    )

            self.last_link_time[user_id] = now

            return

        await self.process_commands(message)

# =========================================================
# BOT INSTANCE
# =========================================================

bot = MyBot()

# =========================================================
# MUTE PERMISSION SYSTEM
# =========================================================

ALLOWED_MUTE_USERS = set()

# =========================================================
# TIME PARSER
# =========================================================

def parse_duration(duration: str):

    duration = duration.lower()

    match = re.match(
        r"(\d+)(s|m|h|d)$",
        duration
    )

    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "s":
        return timedelta(seconds=value)

    if unit == "m":
        return timedelta(minutes=value)

    if unit == "h":
        return timedelta(hours=value)

    if unit == "d":
        return timedelta(days=value)

    return None

# =========================================================
# ADD MUTE PERMISSION
# =========================================================

@bot.command()
async def addmute(ctx, member: discord.Member):

    if ctx.author.id != ctx.guild.owner_id:

        return await ctx.send(
            "❌ فقط مالك السيرفر يستطيع استخدام هذا الامر."
        )

    if member.id in ALLOWED_MUTE_USERS:

        embed = discord.Embed(
            title="⚠️ Already Added",
            description=f"{member.mention} already has mute permissions.",
            color=0xFFFF00
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    ALLOWED_MUTE_USERS.add(member.id)

    embed = discord.Embed(
        title="✅ Permission Added",
        description=f"{member.mention} can now use mute commands.",
        color=0x00FF00
    )

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(
        embed=embed,
        delete_after=6
    )

# =========================================================
# REMOVE MUTE PERMISSION
# =========================================================

@bot.command()
async def removemute(ctx, member: discord.Member):

    if ctx.author.id != ctx.guild.owner_id:

        return await ctx.send(
            "❌ فقط مالك السيرفر يستطيع استخدام هذا الامر."
        )

    if member.id not in ALLOWED_MUTE_USERS:

        embed = discord.Embed(
            title="❌ Not Found",
            description=f"{member.mention} does not have mute permissions.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    ALLOWED_MUTE_USERS.remove(member.id)

    embed = discord.Embed(
        title="✅ Permission Removed",
        description=f"{member.mention} can no longer use mute commands.",
        color=0x00FF00
    )

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(
        embed=embed,
        delete_after=6
    )

# =========================================================
# MUTE COMMAND
# =========================================================

@bot.command(name="mute")
async def mute_command(

    ctx,
    member: discord.Member,
    duration: str,
    *,
    reason="No reason provided"

):

    # Permissions
    if (

        ctx.author.id not in ALLOWED_MUTE_USERS
        and ctx.author.id != ctx.guild.owner_id
        and not ctx.author.guild_permissions.administrator

    ):

        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to use this command.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Self mute
    if member.id == ctx.author.id:

        embed = discord.Embed(
            title="❌ Invalid Action",
            description="You cannot mute yourself.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Owner protection
    if (
        member.guild.owner_id == member.id
        and ctx.author.id != ctx.guild.owner_id
    ):

        embed = discord.Embed(
            title="❌ Invalid Target",
            description="You cannot mute the server owner.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Moderator role check
    if (
        member.top_role >= ctx.author.top_role
        and ctx.author.id != ctx.guild.owner_id
    ):

        embed = discord.Embed(
            title="❌ Role Error",
            description="You cannot mute someone with higher or equal role.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Bot role check
    if member.top_role >= ctx.guild.me.top_role:

        embed = discord.Embed(
            title="❌ Bot Role Error",
            description="My role is lower than the target user.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Duration
    delta = parse_duration(duration)

    if not delta:

        embed = discord.Embed(
            title="❌ Invalid Duration",
            description="Use: `10m`, `1h`, `2d`, `30s`",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    # Apply timeout
    try:

        until = utcnow() + delta

        await member.timeout(
            until,
            reason=reason
        )

        embed = discord.Embed(
            title="🔇 User Muted",
            color=0xFFFF00,
            timestamp=utcnow()
        )

        embed.add_field(
            name="User",
            value=member.mention,
            inline=True
        )

        embed.add_field(
            name="Moderator",
            value=ctx.author.mention,
            inline=True
        )

        embed.add_field(
            name="Duration",
            value=f"`{duration}`",
            inline=True
        )

        embed.add_field(
            name="Reason",
            value=reason,
            inline=False
        )

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.send(embed=embed)

    except Exception as e:

        embed = discord.Embed(
            title="❌ Error",
            description=f"Failed to mute user.\n```{e}```",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.send(
            embed=embed,
            delete_after=6
        )

# =========================================================
# UNMUTE COMMAND
# =========================================================

@bot.command(name="unmute")
async def unmute_command(

    ctx,
    member: discord.Member

):

    if (
        ctx.author.id != ctx.guild.owner_id
        and ctx.author.id not in ALLOWED_MUTE_USERS
        and not ctx.author.guild_permissions.administrator
    ):

        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to use this command.",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        return await ctx.send(
            embed=embed,
            delete_after=6
        )

    try:

        await member.timeout(
            None,
            reason=f"Unmuted by {ctx.author}"
        )

        embed = discord.Embed(
            title="🔊 User Unmuted",
            description=f"{member.mention} has been unmuted.",
            color=0x00FF00,
            timestamp=utcnow()
        )

        embed.add_field(
            name="Moderator",
            value=ctx.author.mention,
            inline=True
        )

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.send(embed=embed)

    except Exception as e:

        embed = discord.Embed(
            title="❌ Error",
            description=f"Failed to unmute user.\n```{e}```",
            color=0xFF0000
        )

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.send(
            embed=embed,
            delete_after=6
        )

# =========================================================
# BASIC COMMANDS
# =========================================================

@bot.command()
async def ping(ctx):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{latency}ms`",
        color=0x00FF00
    )

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(
        embed=embed,
        delete_after=6
    )

@bot.command()
@commands.has_permissions(administrator=True)
async def say(ctx, *, text):

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(
        text,
        allowed_mentions=discord.AllowedMentions.none()
    )

@bot.command()
@commands.has_permissions(administrator=True)
async def servers(ctx):

    embed = discord.Embed(
        title="📊 Servers",
        description=f"Connected to `{len(bot.guilds)}` servers.",
        color=0x3498db
    )

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(
        embed=embed,
        delete_after=6
    )

# =========================================================
# ERRORS
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        return await ctx.send(
            "❌ ليس لديك صلاحية."
        )

    print("Command Error:", error)

# =========================================================
# MAIN
# =========================================================

async def main():

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    asyncio.run(main())
