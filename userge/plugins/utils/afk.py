""" setup AFK mode """

import asyncio
import time
from random import choice, randint

from userge import Config, Message, filters, get_collection, userge
from userge.utils import time_formatter

CHANNEL = userge.getCLogger(__name__)
SAVED_SETTINGS = get_collection("CONFIGS")
AFK_COLLECTION = get_collection("AFK")

IS_AFK = False
IS_AFK_FILTER = filters.create(lambda _, __, ___: bool(IS_AFK))
REASON = ""
TIME = 0.0
USERS = {}


async def _init() -> None:
    global IS_AFK, REASON, TIME  # pylint: disable=global-statement
    data = await SAVED_SETTINGS.find_one({"_id": "AFK"})
    if data:
        IS_AFK = data["on"]
        REASON = data["data"]
        TIME = data["time"] if "time" in data else 0
    async for _user in AFK_COLLECTION.find():
        USERS.update({_user["_id"]: [_user["pcount"], _user["gcount"], _user["men"]]})


@userge.on_cmd(
    "afk",
    about={
        "header": "Set to AFK mode",
        "description": "Sets your status as AFK. Responds to anyone who tags/PM's.\n"
        "you telling you are AFK. Switches off AFK when you type back anything.",
        "usage": "{tr}afk or {tr}afk [reason]",
    },
    allow_channels=False,
)
async def active_afk(message: Message) -> None:
    """turn on or off afk mode"""
    global REASON, IS_AFK, TIME  # pylint: disable=global-statement
    IS_AFK = True
    TIME = time.time()
    REASON = message.input_str
    await asyncio.gather(
        CHANNEL.log(f"You went AFK! : `{REASON}`"),
        message.edit("`You went AFK!`", del_in=1),
        AFK_COLLECTION.drop(),
        SAVED_SETTINGS.update_one(
            {"_id": "AFK"},
            {"$set": {"on": True, "data": REASON, "time": TIME}},
            upsert=True,
        ),
    )


@userge.on_filters(
    IS_AFK_FILTER
    & ~filters.me
    & ~filters.bot
    & ~filters.user(Config.TG_IDS)
    & ~filters.edited
    & (
        filters.mentioned
        | (
            filters.private
            & ~filters.service
            & (
                filters.create(lambda _, __, ___: Config.ALLOW_ALL_PMS)
                | Config.ALLOWED_CHATS
            )
        )
    ),
    allow_via_bot=False,
)
async def handle_afk_incomming(message: Message) -> None:
    """handle incomming messages when you afk"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    chat = message.chat
    user_dict = await message.client.get_user_dict(user_id)
    afk_time = time_formatter(round(time.time() - TIME))
    coro_list = []
    if user_id in USERS:
        if not (USERS[user_id][0] + USERS[user_id][1]) % randint(2, 4):
            if REASON:
                out_str = (
                    f"I'm still **AFK**.\nReason: <code>{REASON}</code>\n"
                    f"Last Seen: `{afk_time} ago`"
                )
            else:
                out_str = choice(AFK_REASONS)
            coro_list.append(message.reply(out_str))
        if chat.type == "private":
            USERS[user_id][0] += 1
        else:
            USERS[user_id][1] += 1
    else:
        if REASON:
            out_str = (
                f"I'm **AFK** right now.\nReason: <code>{REASON}</code>\n"
                f"Last Seen: `{afk_time} ago`"
            )
        else:
            out_str = choice(AFK_REASONS)
        coro_list.append(message.reply(out_str))
        if chat.type == "private":
            USERS[user_id] = [1, 0, user_dict["mention"]]
        else:
            USERS[user_id] = [0, 1, user_dict["mention"]]
    if chat.type == "private":
        coro_list.append(
            CHANNEL.log(
                f"#PRIVATE\n{user_dict['mention']} send you\n\n" f"{message.text}"
            )
        )
    else:
        coro_list.append(
            CHANNEL.log(
                "#GROUP\n"
                f"{user_dict['mention']} tagged you in [{chat.title}](http://t.me/{chat.username})\n\n"
                f"{message.text}\n\n"
                f"[goto_msg](https://t.me/c/{str(chat.id)[4:]}/{message.message_id})"
            )
        )
    coro_list.append(
        AFK_COLLECTION.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "pcount": USERS[user_id][0],
                    "gcount": USERS[user_id][1],
                    "men": USERS[user_id][2],
                }
            },
            upsert=True,
        )
    )
    await asyncio.gather(*coro_list)


@userge.on_filters(IS_AFK_FILTER & filters.outgoing, group=-1, allow_via_bot=False)
async def handle_afk_outgoing(message: Message) -> None:
    """handle outgoing messages when you afk"""
    global IS_AFK  # pylint: disable=global-statement
    IS_AFK = False
    afk_time = time_formatter(round(time.time() - TIME))
    replied: Message = await message.reply("`I'm no longer AFK!`", log=__name__)
    coro_list = []
    if USERS:
        p_msg = ""
        g_msg = ""
        p_count = 0
        g_count = 0
        for pcount, gcount, men in USERS.values():
            if pcount:
                p_msg += f"👤 {men} ✉️ **{pcount}**\n"
                p_count += pcount
            if gcount:
                g_msg += f"👥 {men} ✉️ **{gcount}**\n"
                g_count += gcount
        coro_list.append(
            replied.edit(
                f"`You recieved {p_count + g_count} messages while you were away. "
                f"Check log for more details.`\n\n**AFK time** : __{afk_time}__",
                del_in=3,
            )
        )
        out_str = (
            f"You've recieved **{p_count + g_count}** messages "
            + f"from **{len(USERS)}** users while you were away!\n\n**AFK time** : __{afk_time}__\n"
        )
        if p_count:
            out_str += f"\n**{p_count} Private Messages:**\n\n{p_msg}"
        if g_count:
            out_str += f"\n**{g_count} Group Messages:**\n\n{g_msg}"
        coro_list.append(CHANNEL.log(out_str))
        USERS.clear()
    else:
        await asyncio.sleep(3)
        coro_list.append(replied.delete())
    coro_list.append(
        asyncio.gather(
            AFK_COLLECTION.drop(),
            SAVED_SETTINGS.update_one(
                {"_id": "AFK"}, {"$set": {"on": False}}, upsert=True
            ),
        )
    )
    await asyncio.gather(*coro_list)


AFK_REASONS = (
    "I'm fuckin busy right now. Please talk in a fuckin bag and when I come back you can just give me the fuckin bag!",
    "I'm fuckin away right now. If you fuckin need anything, leave a message after the fuvkin beep: \
`beeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeep!`",
    "You fuckin missed me, next time aim better.",
    "I'll be back in a few minutes and if I'm not...,\nFuckin wait longer.",
    "I'm not here right now, so I'm probably somewhere else.",
    "Roses are yellow,\nViolets are black,\nDon't leave me a a fuckin message,\nI'll noy get back to you.",
    "Sometimes the best things in life are worth waiting for…\nI'll be fuckin right back.",
    "I'll be fuckin back,\nbut if I'm not fuckin back,\nI'll be fuckin back later.",
    "If you haven't figured it out already,\nI'm not here.",
    "I'm away over 7 fuckin seas and 7 fuckin countries,\n7 fuckin waters and 7 fuckin continents,\n7 fuckin mountains and 7 fuckin hills,\
7 fuckin plains and 7 fuckin mounds,\n7 fuckin pools and 7 fuckin lakes,\n7 fuckin springs and 7 fuckin meadows,\
7 fuckin cities and 7 fuckin neighborhoods,\n7 fuckin blocks and 7 fuckin houses...\
    Whereyour fuckin messages can't reach me!",
    "I'm fuckin away from the keyboard at the moment, but if you'll fuckin scream loud enough at your screen,\
    I might just hear you.",
    "I fuckin went that way\n>>>>>",
    "I fuckin went this way\n<<<<<",
    "Please leave a fuckin message and make me feel even more important than I already am.",
    "If I were here,\nI'd tell you where I am.\n\nBut I'm not,\nso fuckin ask me when I return...",
    "I am away!\nI don't know when I'll be back!\nHopefully a few fuckin minutes from now!",
    "I'm not available right now so please leave your fuckin name, number, \
    and address and I will fuckin stalk you later. :P",
    "Sorry, I'm not here right now.\nFeel free to talk to my fuckin userbot as long as you like.\
I'll fuckin get back to you later.",
    "I bet you were expecting an fuckin away message!",
    "Life is fuckin short, there are so many fuckin things to do...\nI'm away doing one of them..",
    "I am not here right now...\nbut if I was...\n\nwouldn't that be fuckin awesome?",
)
