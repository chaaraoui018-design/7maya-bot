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
ALLOWED_CHANNEL_ID = 1403040565137899733

# رابط الريندر
SELF_PING_URL = "https://sevenmaya-bot.onrender.com"

if not TOKEN:
    raise ValueError("Missing DISCORD in environment variables")

# =========================
# Flask Server
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================
# Discord Bot
# =========================

class MyBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix="!", intents=intents)

        # تحذيرات
        self.last_link_time = {}
        self.last_badword_time = {}

        # =========================
        # الكلمات الحساسة
        # =========================

        self.BAD_WORDS = [

            # English
            "fuck","shit","bitch","asshole","bastard","dick","douche",
            "cunt","fag","slut","whore","prick","motherfucker",
            "nigger","cock","pussy","twat","jerk","idiot","moron",
            "dumbass", "نمي",

            # Franco
            "9LAWI","9lawi","zok","zb","MOK","mok",
            "nik","nik mok","9A7BA","9a7ba",
            "zaml","zebi","nikmok",

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
            "ابن العاهرة","ابن الحرام","ابن الزنا"
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
            ".":"",
            ",":""
        }

    async def setup_hook(self):

        self.update_status.start()
        self.self_ping.start()

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

            await self.change_presence(activity=activity)

        except Exception as e:
            print("Status update failed:", e)

    @update_status.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()

    # =========================
    # Self Ping
    # =========================

    @tasks.loop(minutes=5)
    async def self_ping(self):

        try:

            async with aiohttp.ClientSession() as session:

                async with session.get(SELF_PING_URL) as resp:
                    print("Self Ping Status:", resp.status)

        except Exception as e:
            print("Self Ping Failed:", e)

    @self_ping.before_loop
    async def before_self_ping(self):
        await self.wait_until_ready()

    # =========================
    # تنظيف النصوص
    # =========================

    def normalize_text(self, text: str) -> str:

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

        text = re.sub(r"(.)\1{2,}", r"\1", text)

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

        return (
            SequenceMatcher(None, a, b).ratio()
            >= threshold
        )

    # =========================
    # كشف الكلمات الحساسة
    # =========================

    def contains_bad_word(self, text: str) -> bool:

        normalized = self.normalize_text(text)

        words = re.findall(
            r"[a-z0-9\u0621-\u064A]+",
            normalized
        )

        for bad in self.BAD_WORDS:

            bad_norm = self.normalize_text(bad)

            # تطابق مباشر
            if bad_norm in normalized:
                return True

            # تطابق مشابه
            for word in words:

                if self.is_similar(word, bad_norm):
                    return True

        return False

    # =========================
    # كشف الروابط
    # =========================

    def contains_link(self, message: discord.Message) -> bool:

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
            "shorturl.at"
        ]

        full_content = message.content

        for embed in message.embeds:

            if embed.url:
                full_content += " " + embed.url

            if embed.description:
                full_content += " " + embed.description

            if embed.title:
                full_content += " " + embed.title

        content = self.normalize_text(full_content)

        markdown_links = re.findall(
            r"\[.*?\]\((.*?)\)",
            full_content
        )

        for link in markdown_links:

            if not any(
                domain in self.normalize_text(link)
                for domain in spotify_whitelist
            ):
                return True

        patterns = [

            r"h\s*t\s*t\s*p\s*s?\s*:\s*/\s*/",

            r"w\s*w\s*w\s*\.",

            r"https?://",

            r"[a-z0-9\-]+\.(com|net|org|gg|io|me|co|xyz|info|app|site|store|online|tech|dev|link)",

            r"d\s*i\s*s\s*c\s*o\s*r\s*d\s*\.\s*g\s*g"
        ]

        for pat in patterns:

            if re.search(pat, content):
                return True

        for short in shorteners:

            if short in content:
                return True

        for attachment in message.attachments:

            if re.search(
                patterns[3],
                self.normalize_text(attachment.filename)
            ):
                return True

        return False

    # =========================
    # التعامل مع الرسائل
    # =========================

    async def on_message(self, message):

        if message.author.bot:
            return

        user_id = message.author.id

        now = datetime.now(UTC)

        # تجاهل أصحاب الصلاحيات
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

            if message.channel.id == ALLOWED_CHANNEL_ID:

                try:
                    await asyncio.sleep(5)
                    await message.delete()

                except:
                    pass

                return

            try:
                await message.delete()

            except:
                pass

            last_time = self.last_link_time.get(user_id)

            if not last_time or (
                now - last_time
            ) > timedelta(hours=1):

                self.last_link_time[user_id] = now

                embed = discord.Embed(
                    title="⚠️ تحذير من الروابط",
                    description=f"{message.author.mention} نشر الروابط ممنوع. المرة القادمة سيتم اسكاتك.",
                    color=0xFFFF00
                )

                await message.channel.send(embed=embed)

            else:

                try:

                    until_time = utcnow() + timedelta(hours=1)

                    await message.author.timeout(
                        until_time,
                        reason="نشر روابط"
                    )

                    embed = discord.Embed(
                        title="⛔ تم اسكاتك",
                        description=f"{message.author.mention} تم اسكاتك بسبب تكرار نشر الروابط",
                        color=0xFF0000
                    )

                    await message.channel.send(embed=embed)

                except Exception as e:
                    print("Timeout error:", e)

            self.last_link_time[user_id] = now

            return

        # =========================
        # حماية الكلمات الحساسة
        # =========================

        if self.contains_bad_word(message.content):

            try:
                await message.delete()

            except:
                pass

            last_bad = self.last_badword_time.get(user_id)

            if not last_bad or (
                now - last_bad
            ) > timedelta(hours=1):

                self.last_badword_time[user_id] = now

                embed = discord.Embed(
                    title="⚠️ تحذير من الكلمات الحساسة",
                    description=f"{message.author.mention} يمنع استخدام الكلمات المسيئة. المرة القادمة سيتم اسكاتك.",
                    color=0xFFFF00
                )

                await message.channel.send(embed=embed)

            else:

                try:

                    until_time = utcnow() + timedelta(hours=1)

                    await message.author.timeout(
                        until_time,
                        reason="استخدام كلمات مسيئة"
                    )

                    embed = discord.Embed(
                        title="⛔ تم اسكاتك",
                        description=f"{message.author.mention} تم اسكاتك ساعة بسبب تكرار استخدام الكلمات المسيئة.",
                        color=0xFF0000
                    )

                    await message.channel.send(embed=embed)

                except Exception as e:
                    print("Badword timeout error:", e)

            self.last_badword_time[user_id] = now

            return

        await self.process_commands(message)

# =========================
# التشغيل
# =========================

bot = MyBot()

async def main():

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    asyncio.run(main())
