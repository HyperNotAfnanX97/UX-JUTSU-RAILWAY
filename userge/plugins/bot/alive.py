﻿"""Fun plugin"""

import asyncio
from datetime import datetime
from re import compile as comp_regex

from pyrogram import filters
from pyrogram.errors import BadRequest, FloodWait, Forbidden, MediaEmpty
from pyrogram.file_id import PHOTO_TYPES, FileId
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from userge import Config, Message, get_collection, get_version, userge, versions
from userge.core.ext import RawClient
from userge.helpers import msg_type
from userge.plugins.utils.telegraph import upload_media_
from userge.utils import get_file_id, rand_array

_ALIVE_REGEX = comp_regex(
    r"http[s]?://(i\.imgur\.com|telegra\.ph/file|t\.me)/(\w+)(?:\.|/)(gif|jpg|png|jpeg|[0-9]+)(?:/([0-9]+))?"
)
_USER_CACHED_MEDIA, _BOT_CACHED_MEDIA = None, None
media_ = None

SAVED_SETTINGS = get_collection("CONFIGS")

LOGGER = userge.getLogger(__name__)


async def _init() -> None:
    global _USER_CACHED_MEDIA, _BOT_CACHED_MEDIA
    if Config.ALIVE_MEDIA and Config.ALIVE_MEDIA.lower() != "false":
        am_type, am_link = await Bot_Alive.check_media_link(Config.ALIVE_MEDIA.strip())
        if am_type and am_type == "tg_media":
            try:
                if Config.HU_STRING_SESSION:
                    _USER_CACHED_MEDIA = get_file_id(
                        await userge.get_messages(am_link[0], am_link[1])
                    )
            except Exception as u_rr:
                LOGGER.debug(u_rr)
            try:
                if userge.has_bot:
                    _BOT_CACHED_MEDIA = get_file_id(
                        await userge.bot.get_messages(am_link[0], am_link[1])
                    )
            except Exception as b_rr:
                LOGGER.debug(b_rr)


@userge.on_cmd(
    "a_media",
    about={
        "header": "set alive media",
        "flags": {
            "-c": "check alive media.",
            "-r": "reset alive media.",
        },
        "usage": "{tr}a_media [reply to media]",
    },
)
async def set_alive_media(message: Message):
    """set alive media"""
    found = await SAVED_SETTINGS.find_one({"_id": "ALIVE_MEDIA"})
    if "-c" in message.flags:
        if found:
            media_ = found["url"]
        else:
            media_ = "https://telegra.ph/file/1fb4c193b5ac0c593f528.jpg"
        return await message.edit(f"The alive media is set to [<b>THIS</b>]({media_}).")
    elif "-r" in message.flags:
        if not found:
            return await message.edit("`No alive media is set.`", del_in=5)
        await SAVED_SETTINGS.delete_one({"_id": "ALIVE_MEDIA"})
        return await message.edit("`Alive media reset to default.`", del_in=5)
    reply_ = message.reply_to_message
    if not reply_:
        return await message.edit(
            "`Reply to media to set it as alive media.`", del_in=5
        )
    type_ = msg_type(reply_)
    if type_ not in ["gif", "photo"]:
        return await message.edit("`Reply to media only.`", del_in=5)
    link_ = await upload_media_(message)
    whole_link = f"https://telegra.ph{link_}"
    await SAVED_SETTINGS.update_one(
        {"_id": "ALIVE_MEDIA"}, {"$set": {"url": whole_link}}, upsert=True
    )
    await SAVED_SETTINGS.update_one(
        {"_id": "ALIVE_MEDIA"}, {"$set": {"type": type_}}, upsert=True
    )
    link_log = (await reply_.forward(Config.LOG_CHANNEL_ID)).link
    await message.edit(
        f"`Alive media set.` [<b>Preview</b>]({link_log})\n`Bot soft restarting, please wait...`",
        disable_web_page_preview=True,
    )
    asyncio.get_event_loop().create_task(userge.restart())


@userge.on_cmd("alive", about={"header": "Just For Fun"}, allow_channels=False)
async def alive_inline(message: Message):
    try:
        if message.client.is_bot:
            await send_alive_message(message)
        elif userge.has_bot:
            try:
                await send_inline_alive(message)
            except BadRequest:
                await send_alive_message(message)
        else:
            await send_alive_message(message)
    except Exception as e_all:
        await message.err(str(e_all), del_in=10, log=__name__)


async def send_inline_alive(message: Message) -> None:
    _bot = await userge.bot.get_me()
    try:
        i_res = await userge.get_inline_bot_results(_bot.username, "alive")
        i_res_id = (
            (
                await userge.send_inline_bot_result(
                    chat_id=message.chat.id,
                    query_id=i_res.query_id,
                    result_id=i_res.results[0].id,
                )
            )
            .updates[0]
            .id
        )
    except (Forbidden, BadRequest) as ex:
        await message.err(str(ex), del_in=5)
        return
    await message.delete()
    await asyncio.sleep(200)
    await userge.delete_messages(message.chat.id, i_res_id)


async def send_alive_message(message: Message) -> None:
    global _USER_CACHED_MEDIA, _BOT_CACHED_MEDIA
    me = await userge.get_me()
    chat_id = message.chat.id
    client = message.client
    caption = Bot_Alive.alive_info(me)
    if client.is_bot:
        reply_markup = Bot_Alive.alive_buttons()
        file_id = _BOT_CACHED_MEDIA
    else:
        reply_markup = None
        file_id = _USER_CACHED_MEDIA
        caption += (
            f"\n⚡️  <a href={Config.UPSTREAM_REPO}><b>REPO</b></a>"
            "    <code>|</code>    "
            "👥  <a href='https://t.me/useless_x'><b>SUPPORT</b></a>"
        )
    if not Config.ALIVE_MEDIA:
        await client.send_photo(
            chat_id,
            photo=Bot_Alive.alive_default_imgs(),
            caption=caption,
            reply_markup=reply_markup,
        )
        return
    url_ = Config.ALIVE_MEDIA.strip()
    if url_.lower() == "false":
        await client.send_message(
            chat_id,
            caption=caption,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    else:
        type_, media_ = await Bot_Alive.check_media_link(Config.ALIVE_MEDIA)
        if type_ == "url_gif":
            await client.send_animation(
                chat_id,
                animation=url_,
                caption=caption,
                reply_markup=reply_markup,
            )
        elif type_ == "url_image":
            await client.send_photo(
                chat_id,
                photo=url_,
                caption=caption,
                reply_markup=reply_markup,
            )
        elif type_ == "tg_media":
            try:
                await client.send_cached_media(
                    chat_id,
                    file_id=file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
            except MediaEmpty:
                if not message.client.is_bot:
                    try:
                        refeshed_f_id = get_file_id(
                            await userge.get_messages(media_[0], media_[1])
                        )
                        await userge.send_cached_media(
                            chat_id,
                            file_id=refeshed_f_id,
                            caption=caption,
                        )
                    except Exception as u_err:
                        LOGGER.error(u_err)
                    else:
                        _USER_CACHED_MEDIA = refeshed_f_id


if userge.has_bot:

    @userge.bot.on_callback_query(filters.regex(pattern=r"^settings_btn$"))
    async def alive_cb(_, c_q: CallbackQuery):
        me = await userge.get_me()
        allow = bool(
            c_q.from_user
            and (
                c_q.from_user.id in Config.OWNER_ID
                or c_q.from_user.id in Config.SUDO_USERS
            )
        )
        if allow:
            start = datetime.now()
            try:
                await c_q.edit_message_text(
                    Bot_Alive.alive_info(me),
                    reply_markup=Bot_Alive.alive_buttons(),
                    disable_web_page_preview=True,
                )
            except FloodWait as e:
                await asyncio.sleep(e.x)
            except BadRequest:
                pass
            ping = "𝗣𝗶𝗻𝗴:  🏓  {} sec\n"
        alive_s = "➕ 𝗘𝘅𝘁𝗿𝗮 𝗣𝗹𝘂𝗴𝗶𝗻𝘀 : {}\n".format(
            _parse_arg(Config.LOAD_UNOFFICIAL_PLUGINS)
        )
        alive_s += f"👥 𝗦𝘂𝗱𝗼 : {_parse_arg(Config.SUDO_ENABLED)}\n"
        alive_s += f"🚨 𝗔𝗻𝘁𝗶𝘀𝗽𝗮𝗺 : {_parse_arg(Config.ANTISPAM_SENTRY)}\n"
        if Config.HEROKU_APP and Config.RUN_DYNO_SAVER:
            alive_s += "⛽️ 𝗗𝘆𝗻𝗼 𝗦𝗮𝘃𝗲𝗿 :  ✅ 𝙴𝚗𝚊𝚋𝚕𝚎𝚍\n"
        alive_s += f"💬 𝗕𝗼𝘁 𝗙𝗼𝗿𝘄𝗮𝗿𝗱𝘀 : {_parse_arg(Config.BOT_FORWARDS)}\n"
        alive_s += f"🛡 𝗣𝗠 𝗚𝘂𝗮𝗿𝗱 : {_parse_arg(not Config.ALLOW_ALL_PMS)}\n"
        alive_s += f"📝 𝗣𝗠 𝗟𝗼𝗴𝗴𝗲𝗿 : {_parse_arg(Config.PM_LOGGING)}"
        if allow:
            end = datetime.now()
            m_s = (end - start).microseconds / 1000
            await c_q.answer(ping.format(m_s) + alive_s, show_alert=True)
        else:
            await c_q.answer(alive_s, show_alert=True)
        await asyncio.sleep(0.5)


def _parse_arg(arg: bool) -> str:
    return " ✅ 𝙴𝚗𝚊𝚋𝚕𝚎𝚍" if arg else " ❌ 𝙳𝚒𝚜𝚊𝚋𝚕𝚎𝚍"


class Bot_Alive:
    @staticmethod
    async def check_media_link(media_link: str):
        match = _ALIVE_REGEX.search(media_link.strip())
        if not match:
            return None, None
        if match.group(1) == "i.imgur.com":
            link = match.group(0)
            link_type = "url_gif" if match.group(3) == "gif" else "url_image"
        elif match.group(1) == "telegra.ph/file":
            link = match.group(0)
            link_type = "url_image"
        else:
            link_type = "tg_media"
            if match.group(2) == "c":
                chat_id = int("-100" + str(match.group(3)))
                message_id = match.group(4)
            else:
                chat_id = match.group(2)
                message_id = match.group(3)
            link = [chat_id, int(message_id)]
        return link_type, link

    @staticmethod
    def alive_info(me):
        u_name = " ".join([me.first_name, me.last_name or ""])
        alive_info = f"""
­<a href="https://telegra.ph/file/77bbb85f6cf4cc6842c5f.jpg"><b>𝑹𝑰𝑵𝑵𝑬𝑮𝑨𝑵</a> is on and Analysing.</b>

  🐍   <b>Pethon      :</b>    <code>v{versions.__python_version__}</code>
  🔥   <b>Perogram :</b>    <code>v{versions.__pyro_version__}</code>
  🧬   <b>𝑿                :</b>    <code>v{get_version()}</code>
  👤   <b>Master          :</b>    <code>{u_name}</code>
  <b>{Bot_Alive._get_mode()}</b>        <code>|</code>    Uptime  <b>{userge.uptime}</b>
"""
        return alive_info

    @staticmethod
    def _get_mode() -> str:
        if RawClient.DUAL_MODE:
            return "↕️   DUAL"
        if Config.BOT_TOKEN:
            return "🤖  BOT"
        return "👤  USER"

    @staticmethod
    def alive_buttons() -> InlineKeyboardMarkup:
        buttons = [
            [
                InlineKeyboardButton(text="🔧  SETTINGS", callback_data="settings_btn"),
            ],
            [
                InlineKeyboardButton(
                    text="✖️  XPLUGINS", url="t.me/ux_xplugin_support"
                ),
                InlineKeyboardButton(text="⚡  REPO", url=Config.UPSTREAM_REPO),
            ],
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod

    def alive_default_imgs() -> str:

        alive_imgs = [

            "https://telegra.ph/file/028d334c4734482b4237b.jpg",
            "https://telegra.ph/file/2835c93a525681e0b9410.jpg",
            "https://telegra.ph/file/47887c8e7c20b439a8891.jpg",
            "https://telegra.ph/file/d4c0cccba65ab4ce84755.jpg",
            "https://telegra.ph/file/0f9a4f958cc66d1940bf6.jpg",
            "https://telegra.ph/file/e19dd3c48ada5196dc19c.jpg",
            "https://telegra.ph/file/a5cfea1e88a8b497aac77.jpg",
            "https://telegra.ph/file/ae89991978ef4f2c8018b.jpg",
            "https://telegra.ph/file/f0af55233e5c3ada588e0.jpg",
            "https://telegra.ph/file/e90e613955ec9d777bf54.jpg",
            "https://telegra.ph/file/7cd68d150debc02438313.jpg",
            "https://telegra.ph/file/10df5825e6a64cc152dfd.jpg",
            "https://telegra.ph/file/b322f36d8c62a80035f40.jpg",
            "https://telegra.ph/file/5e5bfea85014be87f4800.jpg",
        ]


        return rand_array(alive_imgs)

    @staticmethod

    def get_bot_cached_fid() -> str:

        return _BOT_CACHED_MEDIA

    @staticmethod

    def is_photo(file_id: str) -> bool:

        return bool(FileId.decode(file_id).file_type in PHOTO_TYPES)
