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
from difflib import SequenceMatcher

# =========================
# الإعدادات
# =========================

TOKEN = os.environ.get("DISCORD")

# روم يسمح بالروابط مؤقتاً
ALLOWED_CHANNEL_ID = 1403040565137899733

# رابط الاستضافة
SELF_PING_URL = "https://sevenmaya-bot.onrender.com"

# مدة التايم أوت
TIMEOUT_DURATION = timedelta(hours=1)

# مدة التحذير قبل التايم أوت
WARNING_COOLDOWN = timedelta(hours=1)

if not TOKEN:
    raise ValueError("Missing DISCORD in environment variables")

# =========================
# Flask Server
# =========================

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

# =========================
# Discord Bot
# =========================

class MyBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.all()

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        self.last_link_time = {}
        self.last_badword_time = {}

        # =========================
        # الكلمات الممنوعة
        # =========================

        self.BAD_WORDS = [

            # English
            "fuck","shit","bitch","asshole","bastard","dick","douche",
            "cunt","fag","slut","whore","prick","motherfucker",
            "nigger","cock","pussy","twat","jerk","idiot","moron",
            "dumbass","retard","niga","nigga","fucker","mf",

            # Franco
            "9lawi","zok","zb","mok","nik","nikmok",
            "9a7ba","zaml","zebi","nik mok","nayek",

            # Arabic
            "الطبون","طبون","زبور","الزبور","كلب","نيك",
            "نيك مك","كس","قحبة","ولد القحبة",
            "ابن الكلب","حمار","غبي","قذر","حقير",
            "كافر","زب","زبي","قلاوي","زك",
            "الزك","نكمك","عطاي","حيوان","منيوك",
            "خنزير","خائن","متسكع","أرعن","حقيرة",
            "لعينة","مشين","زانية","أوغاد","أهبل",
            "لعين","منيك","ترمة","مترم","بقرة",
            "شرموطة","الشرموطة","العاهرة",
            "قليل الأدب","ابن الشرموطة",
            "كس أمك","كس اختك",
            "ابن القحبة","ابن الزانية",
            "ابن العاهرة","ابن الحرام","ابن الزنا",
            "ياكلب","ياحمار","متخلف","تافه"
        ]

        # =========================
        # استبدال الرموز
        # =========================

        self.REPLACEMENTS = {

            "@":"a",
            "4":"a",
            "à":"a",
            "á":"a",
            "â":"a",
            "ä":"a",
            "å":"a",

            "8":"b",
            "ß":"b",

            "(":"c",
            "¢":"c",
            "©":"c",
            "ç":"c",

            "3":"e",
            "€":"e",
            "&":"e",
            "ë":"e",
            "è":"e",
            "é":"e",
            "ê":"e",

            "6":"g",
            "9":"g",

            "#":"h",

            "!":"i",
            "1":"i",
            "¡":"i",
            "|":"i",
            "í":"i",
            "î":"i",
            "ï":"i",
            "ì":"i",

            "£":"l",
            "¬":"l",

            "0":"o",
            "ò":"o",
            "ó":"o",
            "ô":"o",
            "ö":"o",
            "ø":"o",

            "$":"s",
            "5":"s",
            "§":"s",
            "š":"s",

            "7":"t",
            "+":"t",
            "†":"t",

            "2":"z",

            "¥":"y",

            "*":"",
            "^":"",
            "~":"",
            "`":"",
            "?":"",
            ",":"",
            "_":"",
            ";":"",
            "'":"",
            "\"":"",
            "\\":"",
            "=":"",
            "%":""
        }

    # =========================
    # تشغيل البوت
    # =========================

    async def setup_hook(self):

        self.update_status.start()
        self.self_ping.start()
        self.cleanup_cache.start()

    async def on_ready(self):

        print("=" * 50)
        print(f"Bot Name : {self.user}")
        print(f"Bot ID   : {self.user.id}")
        print(f"Guilds   : {len(self.guilds)}")
        print("=" * 50)

    # =========================
    # تحديث الحالة
    # =========================

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
            print("Status update failed:", e)

    @update_status.before_loop
    async def before_status_update():
        await bot.wait_until_ready()

    # =========================
    # Self Ping
    # =========================

    @tasks.loop(minutes=5)
    async def self_ping(self):

        try:

            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.get(SELF_PING_URL) as resp:

                    print(
                        f"[SELF PING] Status: {resp.status}"
                    )

        except Exception as e:
            print("Self Ping Failed:", e)

    @self_ping.before_loop
    async def before_self_ping():
        await bot.wait_until_ready()

    # =========================
    # تنظيف الكاش
    # =========================

    @tasks.loop(hours=6)
    async def cleanup_cache(self):

        try:

            now = datetime.now(UTC)

            self.last_link_time = {
                k: v for k, v in self.last_link_time.items()
                if (now - v) < timedelta(days=1)
            }

            self.last_badword_time = {
                k: v for k, v in self.last_badword_time.items()
                if (now - v) < timedelta(days=1)
            }

            print("Cache cleaned")

        except Exception as e:
            print("Cleanup error:", e)

    @cleanup_cache.before_loop
    async def before_cleanup():
        await bot.wait_until_ready()

    # =========================
    # تنظيف النص
    # =========================

    def normalize_text(self, text: str) -> str:

        if not text:
            return ""

        text = text.lower()

        for old, new in self.REPLACEMENTS.items():
            text = text.replace(old, new)

        text = unicodedata.normalize("NFKD", text)

        text = ''.join(
            c for c in text
            if not unicodedata.combining(c)
        )

        text = text.replace("ـ", "")

        text = re.sub(r"\s+", "", text)

        text = re.sub(
            r"(.)\1{2,}",
            r"\1",
            text
        )

        text = re.sub(
            r"[^a-z0-9\u0621-\u064A]+",
            "",
            text
        )

        return text

    # =========================
    # مقارنة الكلمات
    # =========================

    def is_similar(
        self,
        a: str,
        b: str,
        threshold: float = 0.80
    ) -> bool:

        try:

            ratio = SequenceMatcher(
                None,
                a,
                b
            ).ratio()

            return ratio >= threshold

        except:
            return False

    # =========================
    # كشف الكلمات المسيئة
    # =========================

    def contains_bad_word(self, text: str) -> bool:

        normalized = self.normalize_text(text)

        if not normalized:
            return False

        words = re.findall(
            r"[a-z0-9\u0621-\u064A]+",
            normalized
        )

        for bad in self.BAD_WORDS:

            bad_norm = self.normalize_text(bad)

            if bad_norm in normalized:
                return True

            for word in words:

                if self.is_similar(
                    word,
                    bad_norm
                ):
                    return True

        return False

    # =========================
    # كشف الروابط
    # =========================

    def contains_link(
        self,
        message: discord.Message
    ) -> bool:

        spotify_whitelist = [
            "spotify.com",
            "open.spotify.com",
            "spotify.link"
        ]

        shorteners = [
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

        full_content = message.content or ""

        # embeds
        for embed in message.embeds:

            if embed.url:
                full_content += f" {embed.url}"

            if embed.description:
                full_content += f" {embed.description}"

            if embed.title:
                full_content += f" {embed.title}"

        # buttons
        try:

            for row in message.components:

                for item in row.children:

                    if hasattr(item, "url") and item.url:
                        full_content += f" {item.url}"

        except:
            pass

        raw_content = full_content.lower()

        normalized = self.normalize_text(full_content)

        # السماح بروابط سبوتيفاي
        for domain in spotify_whitelist:

            if domain in raw_content:
                return False

        # markdown links
        markdown_links = re.findall(
            r"\[.*?\]\((.*?)\)",
            raw_content
        )

        for link in markdown_links:

            if not any(
                domain in link
                for domain in spotify_whitelist
            ):
                return True

        patterns = [

            r"https?:\/\/[^\s]+",

            r"www\.[^\s]+",

            r"\b[a-zA-Z0-9-]+\.(com|net|org|gg|io|me|co|xyz|info|app|site|store|online|tech|dev|link|ru|tk)\b",

            r"discord\.gg\/[^\s]+",

            r"discord\.com\/invite\/[^\s]+",

            r"h\s*t\s*t\s*p",

            r"w\s*w\s*w"
        ]

        for pattern in patterns:

            if re.search(
                pattern,
                raw_content,
                re.IGNORECASE
            ):
                return True

        normalized_patterns = [

            "https",
            "http",
            "www",
            "discordgg",
            "discordcominvite"
        ]

        for p in normalized_patterns:

            if p in normalized:
                return True

        # shorteners
        for short in shorteners:

            if short in raw_content:
                return True

        # attachments
        for attachment in message.attachments:

            filename = attachment.filename.lower()

            if re.search(
                r"\.(com|net|org|gg|io|xyz|ru|tk)",
                filename
            ):
                return True

        return False

    # =========================
    # إرسال تحذير
    # =========================

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
            print("Warning send error:", e)

    # =========================
    # تايم أوت
    # =========================

    async def apply_timeout(
        self,
        member,
        reason
    ):

        try:

            until_time = utcnow() + TIMEOUT_DURATION

            await member.timeout(
                until_time,
                reason=reason
            )

            return True

        except Exception as e:

            print("Timeout error:", e)
            return False

    # =========================
    # استقبال الرسائل
    # =========================

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

        # تجاهل الإدارة
        if any(
            role.permissions.manage_messages
            for role in message.author.roles
        ):

            await self.process_commands(message)
            return

        # =========================
        # حماية الروابط
        # =========================

        if self.contains_link(message):

            # روم مسموح مؤقت
            if message.channel.id == ALLOWED_CHANNEL_ID:

                try:

                    await asyncio.sleep(5)
                    await message.delete()

                except:
                    pass

                return

            # حذف الرسالة
            try:
                await message.delete()
            except:
                pass

            last_time = self.last_link_time.get(user_id)

            # أول مخالفة
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

        # =========================
        # الكلمات المسيئة
        # =========================

        if self.contains_bad_word(message.content):

            try:
                await message.delete()
            except:
                pass

            last_bad = self.last_badword_time.get(user_id)

            if (
                not last_bad or
                (now - last_bad) > WARNING_COOLDOWN
            ):

                self.last_badword_time[user_id] = now

                await self.send_warning(
                    message.channel,
                    "⚠️ تحذير من الكلمات المسيئة",
                    f"{message.author.mention} يمنع استخدام الكلمات المسيئة. المرة القادمة سيتم اسكاتك.",
                    0xFFFF00
                )

            else:

                success = await self.apply_timeout(
                    message.author,
                    "استخدام كلمات مسيئة"
                )

                if success:

                    await self.send_warning(
                        message.channel,
                        "⛔ تم اسكاتك",
                        f"{message.author.mention} تم اسكاتك ساعة بسبب تكرار استخدام الكلمات المسيئة.",
                        0xFF0000
                    )

            self.last_badword_time[user_id] = now
            return

        await self.process_commands(message)

# =========================
# إنشاء البوت
# =========================

bot = MyBot()

# =========================
# أوامر البوت
# =========================

@bot.command()
async def ping(ctx):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{latency}ms`",
        color=0x00FF00
    )

    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def say(ctx, *, text):

    try:
        await ctx.message.delete()
    except:
        pass

    await ctx.send(text)

@bot.command()
@commands.has_permissions(administrator=True)
async def servers(ctx):

    embed = discord.Embed(
        title="📊 Servers",
        description=f"Connected to `{len(bot.guilds)}` servers.",
        color=0x3498db
    )

    await ctx.send(embed=embed)

# =========================
# أخطاء الأوامر
# =========================

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

# =========================
# التشغيل
# =========================

async def main():

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    asyncio.run(main())
