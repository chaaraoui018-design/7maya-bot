import discord
from discord.ext import commands, tasks
from flask import Flask
import os
import asyncio
import threading
import re
import unicodedata
import aiohttp
import json

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

# ملف حفظ التحذيرات / أوقات العقوبات / إعدادات السيرفرات
DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "warnings.json"
)

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
# STORE  (warnings.json)
# =========================================================

class Store:

    def __init__(self, path):

        self.path = path
        self.lock = threading.Lock()

        self.data = {
            "last_link": {},      # user_id -> وقت آخر رابط
            "last_everyone": {},  # user_id -> وقت آخر منشن عام
            "warns": {},          # user_id -> {count, history}
            "guilds": {}          # guild_id -> {log_channel, allowed_channels}
        }

        self.load()

    # =====================================================
    # LOAD / SAVE
    # =====================================================

    def load(self):

        try:

            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            for key in self.data:

                if isinstance(saved.get(key), dict):
                    self.data[key] = saved[key]

            print(f"[STORE] Loaded: {self.path}")

        except FileNotFoundError:

            print(f"[STORE] New file will be created: {self.path}")

        except Exception as e:

            print("[STORE] Load Error:", e)

    def save(self):

        try:

            with self.lock:

                tmp = self.path + ".tmp"

                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(
                        self.data,
                        f,
                        ensure_ascii=False,
                        indent=2
                    )

                os.replace(tmp, self.path)

        except Exception as e:

            print("[STORE] Save Error:", e)

    # =====================================================
    # GUILD CONFIG
    # =====================================================

    def guild(self, guild_id):

        cfg = self.data["guilds"].setdefault(str(guild_id), {})

        cfg.setdefault("log_channel", None)
        cfg.setdefault("allowed_channels", [])

        return cfg

    def log_channel(self, guild_id):

        if guild_id is None:
            return None

        return self.guild(guild_id)["log_channel"]

    def set_log_channel(self, guild_id, channel_id):

        self.guild(guild_id)["log_channel"] = channel_id
        self.save()

    def allowed_channels(self, guild_id):

        if guild_id is None:
            return []

        return self.guild(guild_id)["allowed_channels"]

    def allow_channel(self, guild_id, channel_id):

        channels = self.allowed_channels(guild_id)

        if channel_id not in channels:
            channels.append(channel_id)
            self.save()

    def is_allowed_channel(self, guild_id, channel_id):

        return (
            channel_id == ALLOWED_CHANNEL_ID
            or channel_id in self.allowed_channels(guild_id)
        )

    # =====================================================
    # COOLDOWN TIMES
    # =====================================================

    def load_times(self, key):

        times = {}

        for user_id, value in self.data.get(key, {}).items():

            try:
                times[int(user_id)] = datetime.fromisoformat(value)
            except Exception:
                pass

        return times

    def save_times(self, key, mapping):

        self.data[key] = {
            str(user_id): when.isoformat()
            for user_id, when in mapping.items()
        }

        self.save()

    def save_time(self, key, user_id, when):

        self.data[key][str(user_id)] = when.isoformat()
        self.save()

    # =====================================================
    # WARNINGS
    # =====================================================

    def add_warn(self, guild_id, user_id, reason, moderator_id):

        entry = self.data["warns"].setdefault(
            str(user_id),
            {"count": 0, "history": []}
        )

        entry.setdefault("history", [])
        entry["count"] = entry.get("count", 0) + 1

        entry["history"].append({
            "guild": str(guild_id),
            "reason": reason,
            "moderator": str(moderator_id),
            "at": datetime.now(UTC).isoformat()
        })

        self.save()

        return entry["count"]

    def warn_count(self, user_id):

        return self.data["warns"].get(str(user_id), {}).get("count", 0)

    def warn_history(self, user_id):

        return self.data["warns"].get(str(user_id), {}).get("history", [])


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

        self.store = Store(DATA_FILE)

        # محفوظة في warnings.json → تبقى بعد أي restart
        self.last_link_time = self.store.load_times("last_link")

        self.last_everyone_time = self.store.load_times("last_everyone")

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

        # تسجيل أوامر السلاش (allowchannel)
        try:

            synced = await self.tree.sync()
            print(f"Slash commands synced: {len(synced)}")

        except Exception as e:

            print("Slash Sync Error:", e)

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

            self.last_everyone_time = {
                k: v
                for k, v in self.last_everyone_time.items()
                if (now - v) < timedelta(days=1)
            }

            self.store.save_times("last_link", self.last_link_time)
            self.store.save_times("last_everyone", self.last_everyone_time)

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
    # SAFE STAFF CHECK
    # =========================================================

    def is_staff(self, member) -> bool:

        # isinstance ضروري: لو الرسالة من User مو Member
        # (مو في كاش السيرفر) كان يطلع AttributeError

        if not isinstance(member, discord.Member):
            return False

        return (
            member.guild_permissions.manage_messages
            or member.guild_permissions.administrator
        )

    # =========================================================
    # @everyone DETECTION
    # =========================================================

    def mentions_everyone(self, message: discord.Message) -> bool:

        content = (message.content or "").lower()

        return (
            message.mention_everyone
            or "@everyone" in content
            or "@here" in content
        )

    # =========================================================
    # LOG CHANNEL
    # =========================================================

    async def send_log(
        self,
        guild,
        title,
        description,
        color,
        fields=None
    ):

        if guild is None:
            return

        channel_id = self.store.log_channel(guild.id)

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:

            try:
                channel = await self.fetch_channel(channel_id)
            except Exception:
                return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=utcnow()
        )

        for name, value in (fields or []):
            embed.add_field(
                name=name,
                value=value,
                inline=True
            )

        embed.set_footer(text=f"🛡️ {guild.name} • Logs")

        try:
            await channel.send(embed=embed)

        except Exception as e:
            print("Log Error:", e)

    # =========================================================
    # @everyone MONITOR  (تحذير → اسكات ساعة)
    # =========================================================

    async def handle_everyone(self, message: discord.Message):

        now = datetime.now(UTC)

        user_id = message.author.id

        try:
            await message.delete()
        except:
            pass

        last_time = self.last_everyone_time.get(user_id)

        first_time = (
            not last_time or
            (now - last_time) > WARNING_COOLDOWN
        )

        self.last_everyone_time[user_id] = now
        self.store.save_time("last_everyone", user_id, now)

        # ---- أول مرة: تحذير ----
        if first_time:

            await self.send_warning(

                message.channel,

                "📢 المنشن العام ممنوع",

                f"{message.author.mention} استخدام `@everyone` / `@here` ممنوع. المرة القادمة سيتم اسكاتك.",

                0xFFFF00
            )

            await self.send_log(

                message.guild,

                "⚠️ تحذير — منشن عام",

                f"{message.author.mention} استخدم منشن عام في {message.channel.mention}",

                0xFFFF00,

                [
                    ("العضو", f"{message.author} (`{user_id}`)"),
                    ("القناة", message.channel.mention),
                    ("العقوبة", "تحذير أول")
                ]
            )

            return

        # ---- تكرار: اسكات ساعة ----
        success = await self.apply_timeout(
            message.author,
            "تكرار استخدام @everyone / @here"
        )

        if success:

            await self.send_warning(

                message.channel,

                "⛔ تم اسكاتك",

                f"{message.author.mention} تم اسكاتك ساعة بسبب تكرار المنشن العام.",

                0xFF0000
            )

            await self.send_log(

                message.guild,

                "⛔ تايم أوت — تكرار منشن عام",

                f"{message.author.mention} تم اسكاته في {message.channel.mention}",

                0xFF0000,

                [
                    ("العضو", f"{message.author} (`{user_id}`)"),
                    ("القناة", message.channel.mention),
                    ("العقوبة", "اسكات 1 ساعة")
                ]
            )


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

        if self.is_staff(message.author) or user_id in ALLOWED_MUTE_USERS:

            await self.process_commands(message)
            return

        # =====================================================
        # @everyone / @here PROTECTION
        # =====================================================

        if self.mentions_everyone(message):

            await self.handle_everyone(message)

        # =====================================================
        # LINK PROTECTION
        # =====================================================

        if self.contains_link(message):

            # Allowed room
            if self.store.is_allowed_channel(
                message.guild.id,
                message.channel.id
            ):

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

                await self.send_log(

                    message.guild,

                    "⚠️ تحذير — نشر رابط",

                    f"{message.author.mention} نشر رابط في {message.channel.mention}",

                    0xFFFF00,

                    [
                        ("العضو", f"{message.author} (`{user_id}`)"),
                        ("القناة", message.channel.mention),
                        ("العقوبة", "تحذير أول")
                    ]
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

                    await self.send_log(

                        message.guild,

                        "⛔ تايم أوت — تكرار الروابط",

                        f"{message.author.mention} تم اسكاته في {message.channel.mention}",

                        0xFF0000,

                        [
                            ("العضو", f"{message.author} (`{user_id}`)"),
                            ("القناة", message.channel.mention),
                            ("العقوبة", "اسكات 1 ساعة")
                        ]
                    )

            self.last_link_time[user_id] = now
            self.store.save_time("last_link", user_id, now)

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
       member.top_role > ctx.author.top_role
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
# COMMAND DESCRIPTIONS  (for !help)
# =========================================================

COMMAND_HELP = {

    "help": "عرض كل الأوامر المتاحة",
    "warn": "تحذير عضو: !warn @user السبب",
    "warns": "عرض تحذيرات عضو: !warns @user",
    "clear": "حذف رسائل: !clear 50",
    "allowchannel": "السماح بالروابط في قناة: !allowchannel #links",
    "setchannellogs": "تحديد قناة اللوقز: !setchannellogs #logs",
    "mute": "اسكات عضو: !mute @user 1h السبب",
    "unmute": "فك الاسكات: !unmute @user",
    "addmute": "السماح لعضو باستخدام أوامر الاسكات",
    "removemute": "سحب صلاحية الاسكات من عضو",
    "ping": "سرعة البوت",
    "say": "إرسال رسالة باسم البوت (أدمن)",
    "servers": "عدد السيرفرات (أدمن)"
}

# =========================================================
# HELP
# =========================================================

@bot.command(name="help")
async def help_command(ctx):

    embed = discord.Embed(
        title="📖 قائمة الأوامر",
        description=f"البريفكس: `{ctx.prefix}`",
        color=0x3498DB,
        timestamp=utcnow()
    )

    for command in sorted(bot.commands, key=lambda c: c.name):

        if command.hidden:
            continue

        signature = f"{ctx.prefix}{command.name} {command.signature}".strip()

        description = (
            command.help
            or COMMAND_HELP.get(command.name)
            or "—"
        )

        embed.add_field(
            name=f"`{signature}`",
            value=description,
            inline=False
        )

    embed.set_footer(text=f"🛡️ {len(bot.commands)} أمر")

    await ctx.send(embed=embed)

# =========================================================
# WARN
# =========================================================

@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_command(
    ctx,
    member: discord.Member,
    *,
    reason="بدون سبب"
):

    count = bot.store.add_warn(
        ctx.guild.id,
        member.id,
        reason,
        ctx.author.id
    )

    embed = discord.Embed(
        title="⚠️ تحذير",
        description=f"{member.mention} تم تحذيره بواسطة {ctx.author.mention}",
        color=0xFFFF00,
        timestamp=utcnow()
    )

    embed.add_field(name="السبب", value=reason, inline=False)
    embed.add_field(name="عدد التحذيرات", value=str(count), inline=True)

    await ctx.send(embed=embed)

    await bot.send_log(
        ctx.guild,
        "⚠️ تحذير عضو",
        f"{member.mention} تم تحذيره بواسطة {ctx.author.mention}",
        0xFFFF00,
        [
            ("العضو", f"{member} (`{member.id}`)"),
            ("بواسطة", f"{ctx.author} (`{ctx.author.id}`)"),
            ("السبب", reason),
            ("العدد", str(count))
        ]
    )

    try:
        await member.send(
            f"⚠️ تم تحذيرك في **{ctx.guild.name}**\n"
            f"السبب: {reason}\n"
            f"عدد تحذيراتك: {count}"
        )
    except:
        pass

# =========================================================
# WARNS
# =========================================================

@bot.command(name="warns")
async def warns_command(ctx, member: discord.Member):

    count = bot.store.warn_count(member.id)

    embed = discord.Embed(
        title="📋 سجل التحذيرات",
        description=f"{member.mention} لديه **{count}** تحذير",
        color=0x3498DB,
        timestamp=utcnow()
    )

    await ctx.send(embed=embed)

# =========================================================
# CLEAR
# =========================================================

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_command(ctx, amount: int = 10):

    amount = max(1, min(amount, 100))

    try:

        deleted = await ctx.channel.purge(limit=amount + 1)

    except Exception as e:

        print("Purge Error:", e)

        return await ctx.send(
            embed=discord.Embed(
                title="⛔ فشل الحذف",
                description="تأكد أن البوت يملك صلاحية **Manage Messages**.",
                color=0xFF0000
            ),
            delete_after=6
        )

    real = max(0, len(deleted) - 1)

    embed = discord.Embed(
        title="🧹 تم التنظيف",
        description=f"تم حذف **{real}** رسالة بواسطة {ctx.author.mention}",
        color=0x2ECC71,
        timestamp=utcnow()
    )

    message = await ctx.send(embed=embed)

    await bot.send_log(
        ctx.guild,
        "🧹 تنظيف رسائل",
        f"{ctx.author.mention} حذف **{real}** رسالة في {ctx.channel.mention}",
        0x2ECC71,
        [
            ("بواسطة", f"{ctx.author} (`{ctx.author.id}`)"),
            ("القناة", ctx.channel.mention),
            ("العدد", str(real))
        ]
    )

    await asyncio.sleep(4)

    try:
        await message.delete()
    except:
        pass

# =========================================================
# ALLOW CHANNEL
# =========================================================

@bot.hybrid_command(
    name="allowchannel",
    description="السماح بالروابط في قناة (تُحذف بعد 5 ثواني بدون عقوبة)"
)
@commands.has_permissions(manage_guild=True)
async def allowchannel_command(
    ctx,
    channel: discord.TextChannel = None
):

    channel = channel or ctx.channel

    bot.store.allow_channel(ctx.guild.id, channel.id)

    embed = discord.Embed(
        title="✅ قناة مسموحة",
        description=(
            f"{channel.mention} صارت مسموحة للروابط\n"
            f"الروابط فيها تُحذف بعد 5 ثواني بدون أي عقوبة."
        ),
        color=0x2ECC71,
        timestamp=utcnow()
    )

    await ctx.send(embed=embed)

    await bot.send_log(
        ctx.guild,
        "✅ قناة مسموحة للروابط",
        f"{ctx.author.mention} أضاف {channel.mention}",
        0x2ECC71,
        [
            ("بواسطة", f"{ctx.author} (`{ctx.author.id}`)"),
            ("القناة", channel.mention)
        ]
    )

# =========================================================
# SET LOG CHANNEL
# =========================================================

@bot.command(name="setchannellogs")
@commands.has_permissions(administrator=True)
async def setchannellogs_command(
    ctx,
    channel: discord.TextChannel = None
):

    channel = channel or ctx.channel

    bot.store.set_log_channel(ctx.guild.id, channel.id)

    embed = discord.Embed(
        title="✅ قناة اللوقز",
        description=f"تم تحديد {channel.mention} كقناة لوقز لهذا السيرفر.",
        color=0x2ECC71,
        timestamp=utcnow()
    )

    await ctx.send(embed=embed)

    # رسالة تجريبية في قناة اللوقز
    await bot.send_log(
        ctx.guild,
        "🔧 تم تفعيل اللوقز",
        f"هذه القناة صارت تستقبل كل أحداث الحماية.\nبواسطة {ctx.author.mention}",
        0x3498DB,
        [
            ("السيرفر", ctx.guild.name),
            ("بواسطة", f"{ctx.author} (`{ctx.author.id}`)")
        ]
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
            embed=discord.Embed(
                title="❌ ليس لديك صلاحية.",
                color=0xFF0000
            ),
            delete_after=6
        )

    if isinstance(
        error,
        commands.MemberNotFound
    ):

        return await ctx.send(
            embed=discord.Embed(
                title="⚠️ العضو غير موجود.",
                description="منشن العضو بشكل صحيح.",
                color=0xFFFF00
            ),
            delete_after=6
        )

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        return await ctx.send(
            embed=discord.Embed(
                title="⚠️ ناقص",
                description=f"استخدم: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                color=0xFFFF00
            ),
            delete_after=6
        )

    if isinstance(
        error,
        commands.BadArgument
    ):

        return await ctx.send(
            embed=discord.Embed(
                title="⚠️ قيمة غير صحيحة",
                description="تأكد من المنشن أو القناة.",
                color=0xFFFF00
            ),
            delete_after=6
        )

    print("Command Error:", error)

# =========================================================
# SLASH ERRORS
# =========================================================

@bot.tree.error
async def on_tree_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(error, commands.MissingPermissions):

        message = "❌ ليس لديك صلاحية."
        color = 0xFF0000

    elif isinstance(error, commands.MemberNotFound):

        message = "⚠️ العضو غير موجود."
        color = 0xFFFF00

    elif isinstance(error, commands.BadArgument):

        message = "⚠️ قيمة غير صحيحة — تأكد من المنشن أو القناة."
        color = 0xFFFF00

    elif isinstance(error, commands.CommandOnCooldown):

        message = f"⏳ انتظر {error.retry_after:.1f} ثانية."
        color = 0xFFFF00

    else:

        print("Slash Error:", error)
        message = "❌ صار خطأ غير متوقع."
        color = 0xFF0000

    embed = discord.Embed(
        title="خطأ",
        description=message,
        color=color
    )

    try:

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

    except Exception as e:

        print("Tree Error Reply:", e)

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
