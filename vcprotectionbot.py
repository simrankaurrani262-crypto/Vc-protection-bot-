#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║          VC BAN BOT - WORKING VERSION                               ║
║     Text + Voice Chat Anonymous User Protection                     ║
║     With Force Join System & Colorful Buttons                       ║
╚══════════════════════════════════════════════════════════════════════╝

YE BOT KAISE KAAM KARTA HAI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Problem: Telegram Bot API VC participants directly show nahi karta.
Solution: Anonymous user ko GROUP se ban karo → VC se bhi kick ho jayega!

NEW FEATURES:
━━━━━━━━━━━━━
🎯 Force Join System - Users must join channel & group before using bot
🌈 Colorful Inline Buttons - Beautiful emoji-themed buttons
📢 Support Channel & Group Links - Easy access to community

LAYERS OF PROTECTION:
━━━━━━━━━━━━━━━━━━━━━━
1. TEXT messages se anonymous channel users detect → Ban
2. NEW members joining group → Instant check → Ban if anonymous
3. Chat member status changes → Detect → Ban
4. /scan command → Existing anonymous users find → Ban
5. Voice chat start hone par → Auto-alert + proactive scan
6. FORCE JOIN → Bot use karne se pehle channel/group join karna mandatory

IS BOT KO CHALANE KE LIYE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━
    pip install python-telegram-bot

SETUP:
━━━━━━
1. Niche BOT_TOKEN mein apna token daalo
2. FORCE_JOIN_CHANNEL aur FORCE_JOIN_GROUP mein apne links daalo
3. python vc_ban_bot_fixed.py run karo
4. Bot ko group mein admin banao with "Ban Users" permission
5. @BotFather se Group Privacy OFF karo
"""
import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Set, Dict

from telegram import (
    Update,
    ChatMember,
    ChatMemberUpdated,
    User,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import Forbidden, BadRequest
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ============================================================================
# CONFIGURATION
# ============================================================================

# Aapka bot token (@BotFather se)
BOT_TOKEN = "8976419802:AAHaTkBlsSBVh8m4kfbzsKRIlOQHCLgwAFQ"

# 🎯 FORCE JOIN SETTINGS
# Bot use karne se pehle users ko yeh channels join karne honge
FORCE_JOIN_ENABLED = True          # Force join system ON/OFF
FORCE_JOIN_CHANNEL = "-1004344057397"  # Support Channel ID (numeric)
FORCE_JOIN_GROUP = "-1002811434860"    # Support Group ID (numeric)

# Force Join messages customize karne ke liye
FORCE_JOIN_CHANNEL_USERNAME = "Globall_X"        # Channel username (bina @ ke)
FORCE_JOIN_GROUP_USERNAME = "Globall_X_Support"  # Group username (bina @ ke)

# Support links (buttons ke liye)
SUPPORT_CHANNEL_LINK = "https://t.me/Globall_X"
SUPPORT_GROUP_LINK = "https://t.me/Globall_X_Support"

# Ban settings
BAN_ANONYMOUS_TEXT = True      # Text mein anonymous users ban kare?
BAN_ON_JOIN = True             # Join karte hi anonymous user ban?
DELETE_ABUSE_MESSAGES = True   # Gali wale messages delete kare?
NOTIFY_GROUP = True            # Group mein ban notification bheje?

# Abuse keywords (Hindi + English)
ABUSE_KEYWORDS = [
    "mc", "bc", "madarchod", "behenchod", "bhenchod",
    "chutiya", "chutiye", "randi", "randwe", "bhosdike",
    "laude", "lund", "gandu", "kutta", "kamine",
    "suar", "harami", "hijda", "chakka", "namard",
    "bhosdi", "lavde", "tatte", "gaand", "choot", "bur",
    "fuck", "fuk", "shit", "bitch", "bastard", "asshole",
    "motherfucker", "cunt", "dick", "pussy",
    "nigga", "nigger", "whore", "slut",
]

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VCBanBot")

# ============================================================================
# TRACKING
# ============================================================================
# Recently banned users (duplicate ban se bachne ke liye)
recently_banned: Set[int] = set()
banned_count: Dict[int, int] = {}  # chat_id -> count


# ============================================================================
# 🌈 COLORFUL INLINE KEYBOARDS FACTORY
# ============================================================================

def force_join_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    🌈 Colorful Force Join inline keyboard buttons.
    Telegram mein direct colored buttons nahi hote, par emojis se colorful look dete hain!
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔴 Join Support Channel",
                url=SUPPORT_CHANNEL_LINK
            ),
        ],
        [
            InlineKeyboardButton(
                text="🟢 Join Support Group",
                url=SUPPORT_GROUP_LINK
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔵 I Have Joined ✅",
                callback_data=f"check_join_{user_id}"
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def support_links_keyboard() -> InlineKeyboardMarkup:
    """🌈 Support channel and group links keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="📢 Support Channel",
                url=SUPPORT_CHANNEL_LINK
            ),
        ],
        [
            InlineKeyboardButton(
                text="💬 Support Group",
                url=SUPPORT_GROUP_LINK
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def colorful_menu_keyboard() -> InlineKeyboardMarkup:
    """🌈 Colorful main menu buttons"""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Stats", callback_data="menu_stats"),
            InlineKeyboardButton(text="🔍 Scan", callback_data="menu_scan"),
        ],
        [
            InlineKeyboardButton(text="🛡️ Help", callback_data="menu_help"),
            InlineKeyboardButton(text="🤖 Test", callback_data="menu_test"),
        ],
        [
            InlineKeyboardButton(text="📢 Support Channel 🔴", url=SUPPORT_CHANNEL_LINK),
        ],
        [
            InlineKeyboardButton(text="💬 Support Group 🟢", url=SUPPORT_GROUP_LINK),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_action_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """🌈 Admin action buttons with colorful emojis"""
    keyboard = [
        [
            InlineKeyboardButton(text="🚫 Ban User", callback_data=f"ban_{user_id}"),
            InlineKeyboardButton(text="🔇 Mute User", callback_data=f"mute_{user_id}"),
        ],
        [
            InlineKeyboardButton(text="⚠️ Warn User", callback_data=f"warn_{user_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================================
# 🎯 FORCE JOIN SYSTEM
# ============================================================================

async def is_user_joined(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: str
) -> bool:
    """
    Check kare ki user ne channel/group join kiya hai ya nahi.
    
    Returns:
        True if user is a member, False otherwise
    """
    try:
        member = await context.bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
        # Status check: member, administrator, creator sab valid hain
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except BadRequest as e:
        # Agar chat nahi mila toh (bot not in group, etc.)
        if "chat not found" in str(e).lower():
            logger.error(f"❌ Chat not found: {chat_id}. Bot ko channel/group mein admin banao!")
        elif "user not found" in str(e).lower():
            logger.warning(f"⚠️ User {user_id} not found in chat {chat_id}")
        else:
            logger.error(f"❌ Error checking membership: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in is_user_joined: {e}")
        return False


async def check_force_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    """
    🎯 Main Force Join check function.
    
    Returns:
        True if user passed force join check
        False if user needs to join (sends force join message)
    """
    if not FORCE_JOIN_ENABLED:
        return True
    
    # Dono channel aur group check karo
    channel_joined = await is_user_joined(context, user_id, FORCE_JOIN_CHANNEL)
    group_joined = await is_user_joined(context, user_id, FORCE_JOIN_GROUP)
    
    if channel_joined and group_joined:
        # User ne dono join kar liye ✅
        return True
    
    # User ne join nahi kiya - force join message bhejo
    not_joined_text = ""
    if not channel_joined:
        not_joined_text += "🔴 <b>Support Channel</b> - Not Joined ❌\n"
    else:
        not_joined_text += "🔴 <b>Support Channel</b> - Joined ✅\n"
    
    if not group_joined:
        not_joined_text += "🟢 <b>Support Group</b> - Not Joined ❌\n\n"
    else:
        not_joined_text += "🟢 <b>Support Group</b> - Joined ✅\n\n"
    
    force_msg = (
        f"🚫 <b>Access Denied!</b>\n\n"
        f"👋 Hi {update.effective_user.mention_html()}!\n\n"
        f"🎯 <b>To use this bot, you must join our community first:</b>\n\n"
        f"{not_joined_text}"
        f"📌 <b>Steps:</b>\n"
        f"1️⃣ Click the buttons below to join\n"
        f"2️⃣ Come back and click ✅ I Have Joined\n\n"
        f"<i>⚠️ This is mandatory to prevent spam!</i>"
    )
    
    try:
        await update.message.reply_text(
            force_msg,
            parse_mode="HTML",
            reply_markup=force_join_keyboard(user_id),
        )
    except Exception as e:
        logger.error(f"Could not send force join message: {e}")
    
    return False


async def handle_force_join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    🔵 Jab user "I Have Joined" button click kare
    """
    query = update.callback_query
    await query.answer()  # Loading state hatao
    
    # Extract user_id from callback_data: "check_join_{user_id}"
    callback_data = query.data
    try:
        expected_user_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ Invalid callback data!", show_alert=True)
        return
    
    user_id = query.from_user.id
    
    # Security check: user apna hi button click kar sakta hai
    if user_id != expected_user_id:
        await query.answer("❌ Ye button aapke liye nahi hai!", show_alert=True)
        return
    
    # Check karo ki user ne sach mein join kiya hai
    channel_joined = await is_user_joined(context, user_id, FORCE_JOIN_CHANNEL)
    group_joined = await is_user_joined(context, user_id, FORCE_JOIN_GROUP)
    
    if channel_joined and group_joined:
        # ✅ User ne dono join kar liye
        welcome_msg = (
            f"✅ <b>Verification Successful!</b>\n\n"
            f"🎉 Welcome {query.from_user.mention_html()}!\n\n"
            f"🔴 Channel: Joined ✅\n"
            f"🟢 Group: Joined ✅\n\n"
            f"🛡️ <b>Bot Features:</b>\n"
            f"• Anonymous users → Auto Ban\n"
            f"• Abuse detection → Auto Mute\n"
            f"• Voice Chat protection → Active\n\n"
            f"Use /help for all commands!"
        )
        
        # Message ko edit karo (replace force join message)
        try:
            await query.edit_message_text(
                welcome_msg,
                parse_mode="HTML",
                reply_markup=support_links_keyboard(),
            )
        except BadRequest:
            # Agar message same hai toh naya bhejo
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=welcome_msg,
                parse_mode="HTML",
                reply_markup=support_links_keyboard(),
            )
    else:
        # ❌ User ne abhi bhi join nahi kiya
        not_joined_text = ""
        if not channel_joined:
            not_joined_text += "🔴 <b>Support Channel</b> - Still Not Joined ❌\n"
        else:
            not_joined_text += "🔴 <b>Support Channel</b> - Joined ✅\n"
        
        if not group_joined:
            not_joined_text += "🟢 <b>Support Group</b> - Still Not Joined ❌\n\n"
        else:
            not_joined_text += "🟢 <b>Support Group</b> - Joined ✅\n\n"
        
        retry_msg = (
            f"❌ <b>Not Joined Yet!</b>\n\n"
            f"{not_joined_text}"
            f"⚠️ Please join both channels first, then click ✅ I Have Joined\n\n"
            f"<i>Make sure you have actually joined, not just clicked!</i>"
        )
        
        await query.edit_message_text(
            retry_msg,
            parse_mode="HTML",
            reply_markup=force_join_keyboard(user_id),
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_recently_banned(user_id: int) -> bool:
    """Check kare ki user recently banned toh nahi"""
    return user_id in recently_banned


def mark_banned(user_id: int):
    """User ko banned list mein daalo aur cooldown set karo"""
    recently_banned.add(user_id)
    # 10 minute baad cooldown se hata do
    asyncio.create_task(_remove_cooldown(user_id))


async def _remove_cooldown(user_id: int):
    """Cooldown period ke baad user ID hatao"""
    await asyncio.sleep(600)  # 10 minutes
    recently_banned.discard(user_id)


def contains_abuse(text: str) -> bool:
    """Check kare ki message mein abuse/gali hai"""
    if not text:
        return False
    text_lower = text.lower()
    for keyword in ABUSE_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


async def safe_ban_chat_member(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    revoke_messages: bool = True,
) -> bool:
    """
    Safe ban function with detailed error handling.
    Channel ID se aaye premium user ko ban karne ke liye.
    Returns True if ban successful, False otherwise.
    """
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            revoke_messages=revoke_messages,
        )
        return True
    except Forbidden as e:
        err_msg = str(e).lower()
        if "bot is not a member" in err_msg:
            logger.error(f"❌ Bot group {chat_id} ka member nahi hai")
        elif "bot is not an administrator" in err_msg:
            logger.error(f"❌ Bot group {chat_id} mein admin nahi hai")
        else:
            logger.error(f"❌ Bot ko 'Ban Users' permission nahi mila chat {chat_id} mein | Error: {e}")
        return False
    except BadRequest as e:
        err_msg = str(e)
        if "Not enough rights" in err_msg:
            logger.error(f"❌ Bot ke paas ban karne ka right nahi hai. Admin > 'Ban Users' permission check karo.")
        elif "USER_ADMIN_INVALID" in err_msg:
            logger.warning(f"⚠️ User {user_id} admin hai ya invalid hai, ban nahi kar sakte")
        elif "Participant_id_invalid" in err_msg:
            logger.warning(f"⚠️ Invalid participant ID: {user_id}")
        elif "can't remove chat owner" in err_msg:
            logger.warning(f"⚠️ Chat owner {user_id} ko ban nahi kar sakte")
        elif "user not found" in err_msg.lower():
            logger.warning(f"⚠️ User {user_id} group mein nahi mila")
        else:
            logger.error(f"❌ Ban failed for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error banning {user_id}: {e}")
        return False


async def safe_delete_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> bool:
    """Safely delete a message"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as e:
        logger.warning(f"Could not delete message {message_id}: {e}")
        return False


# ============================================================================
# CORE BAN LOGIC
# ============================================================================

async def ban_anonymous_entity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entity_id: int,
    entity_name: str,
    source: str,
) -> bool:
    """
    Main ban function - anonymous/premium entity ko group se BAN karo.

    Args:
        entity_id: Channel/User ID to ban
        entity_name: Display name
        source: Detection source (Text/Join/Scan/etc)

    Returns:
        True if banned successfully
    """
    chat_id = update.effective_chat.id

    logger.info(f"🔨 BAN ATTEMPT | Entity: {entity_name} (ID: {entity_id}) | Chat: {chat_id} | Source: {source}")

    # Duplicate check (cooldown)
    if is_recently_banned(entity_id):
        logger.info(f"⏭️ Entity {entity_id} recently banned (cooldown), skipping")
        return False

    # Ban attempt
    success = await safe_ban_chat_member(context, chat_id, entity_id)

    if success:
        mark_banned(entity_id)
        banned_count[chat_id] = banned_count.get(chat_id, 0) + 1

        # Group notification
        if NOTIFY_GROUP:
            try:
                msg = (
                    f"🚫 <b>Premium User BANNED</b>\n\n"
                    f"👤 User: <code>{entity_name}</code>\n"
                    f"🆔 ID: <code>{entity_id}</code>\n"
                    f"📍 Trigger: {source}\n"
                    f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"⚠️ <b>Reason:</b> Channel ID se message bheja.\n"
                    f"🎙️ Ye user VC se bhi kick ho gaya hai.\n\n"
                    f"<i>⚡ Real account se aao — anonymous messages allowed nahi hai.</i>"
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=support_links_keyboard(),
                )
            except Exception as e:
                logger.warning(f"Could not send ban notification: {e}")

        logger.warning(f"✅ BANNED SUCCESSFULLY: {entity_name} (ID: {entity_id}) | Source: {source}")
        return True
    else:
        logger.error(f"❌ BAN FAILED: {entity_name} (ID: {entity_id}) | Check bot permissions!")
        return False


# ============================================================================
# HANDLER 1: ANONYMOUS CHANNEL TEXT MESSAGES
# ============================================================================

async def handle_anonymous_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Jab koi premium user apne channel ke zariye (anonymous) text message bheje,
    usko turant group se BAN karo. Message delete bhi karo.
    """
    message = update.message
    chat = update.effective_chat

    if not message or not message.sender_chat:
        return

    sender_chat = message.sender_chat

    # ✅ Channel type check (string comparison)
    if sender_chat.type != "channel":
        return

    channel_id = sender_chat.id
    channel_title = getattr(sender_chat, 'title', None) or "Unknown Channel"

    logger.info(
        f"🚫 PREMIUM/ANONYMOUS msg detected | "
        f"Channel: {channel_title} (ID: {channel_id}) | "
        f"Banning user NOW..."
    )

    # ===== PEHLE BAN KARO, PHIR DELETE KARO =====
    # (Agar pehle delete kar diya toh update mein message info lost ho jayegi)

    if BAN_ANONYMOUS_TEXT:
        # 🔴 STEP 1: User ko BAN karo (priority #1)
        ban_success = await ban_anonymous_entity(
            update=update,
            context=context,
            entity_id=channel_id,
            entity_name=channel_title,
            source="Premium User - Channel Message (Auto-Ban)",
        )

        if ban_success:
            logger.info(f"✅ BANNED: {channel_title} (ID: {channel_id})")
        else:
            logger.warning(f"❌ BAN FAILED for: {channel_title} (ID: {channel_id})")

    # 🗑️ STEP 2: Message delete karo (ban ke baad)
    await safe_delete_message(context, chat.id, message.message_id)


# ============================================================================
# HANDLER 2: CHAT MEMBER UPDATES (Join/Leave/Status Change)
# ============================================================================

async def handle_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Jab koi user group mein join kare ya uska status change ho.
    Isse hum anonymous users ko unke join karte hi detect kar sakte hain.
    """
    if not update.chat_member:
        return
    
    old_member: ChatMember = update.chat_member.old_chat_member
    new_member: ChatMember = update.chat_member.new_chat_member
    chat: Chat = update.chat_member.chat
    
    # Skip private chats
    if chat.type == "private":
        return
    
    user: User = new_member.user
    
    # ========================================================================
    # DETECTION 1: User joined the group
    # ========================================================================
    is_new_join = (
        old_member.status in ["left", "kicked"] and
        new_member.status in ["member", "restricted"]
    )
    
    if is_new_join and BAN_ON_JOIN:
        logger.info(f"👤 New member joined: {user.full_name} (ID: {user.id})")
        
        # Check karo ki user anonymous toh nahi
        # Telegram mein jab user channel se join hota hai, toh
        # user ka profile kuch specific patterns follow karta hai
        
        # Check 1: User ka username nahi hai (common for anonymous accounts)
        # Check 2: User ka first name generic hai
        # Check 3: User ka account recently bana ho
        
        # Most reliable: Try to get chat member with full details
        try:
            member_info = await context.bot.get_chat_member(chat.id, user.id)
            
            # Agar member anonymous admin hai with channel signature
            if member_info.is_anonymous and member_info.status not in ["creator", "administrator"]:
                logger.info(f"🎭 Anonymous member detected on join: {user.full_name}")
                await ban_anonymous_entity(
                    update=update,
                    context=context,
                    entity_id=user.id,
                    entity_name=user.full_name,
                    source="Anonymous Join Detection",
                )
                return
                
        except Exception as e:
            logger.debug(f"Could not get member info: {e}")
    
    # ========================================================================
    # DETECTION 2: User became anonymous admin
    # ========================================================================
    was_not_anon = not getattr(old_member, 'is_anonymous', False)
    is_now_anon = getattr(new_member, 'is_anonymous', False)
    
    if was_not_anon and is_now_anon:
        logger.info(f"🎭 User {user.full_name} became anonymous!")
        # Admin hai toh ban nahi kar sakte, par log kar sakte hain
        if new_member.status not in ["creator", "administrator"]:
            await ban_anonymous_entity(
                update=update,
                context=context,
                entity_id=user.id,
                entity_name=user.full_name,
                source="Became Anonymous",
            )


# ============================================================================
# HANDLER 3: MY CHAT MEMBER (Bot's own status changes)
# ============================================================================

async def handle_my_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Jab bot ka khud ka status change ho group mein"""
    if not update.my_chat_member:
        return
    
    new_status = update.my_chat_member.new_chat_member.status
    chat = update.my_chat_member.chat
    
    if new_status == "administrator":
        logger.info(f"✅ Bot became admin in: {chat.title}")
        try:
            welcome_msg = (
                "✅ <b>VC Ban Bot Active!</b>\n\n"
                "🛡️ Protection enabled:\n"
                "• Anonymous text users → Auto Ban ✅\n"
                "• Anonymous joiners → Auto Ban ✅\n"
                "• Abuse detection → Auto Delete ✅\n\n"
                "Bot ko ban users ka right mil gaya hai."
            )
            await context.bot.send_message(
                chat_id=chat.id,
                text=welcome_msg,
                parse_mode="HTML",
                reply_markup=support_links_keyboard(),
            )
        except Exception:
            pass
    
    elif new_status in ["left", "kicked"]:
        logger.info(f"⚠️ Bot removed from: {chat.title}")


# ============================================================================
# HANDLER 4: VOICE CHAT EVENTS
# ============================================================================

async def handle_voice_chat_started(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Jab voice chat start ho, ek alert bhejo aur scan karo.
    
    Note: Telegram Bot API VC participants directly list nahi karta.
    Lekin jab VC start hota hai, hum proactive scan kar sakte hain.
    """
    chat = update.effective_chat
    
    logger.info(f"🎙️ Voice Chat started in: {chat.title}")
    
    try:
        # Group ko alert karo
        msg = (
            "🎙️ <b>Voice Chat Started!</b>\n\n"
            "🛡️ <b>Security Alert:</b>\n"
            "Anonymous users are NOT allowed in voice chat.\n\n"
            "⚡ If any anonymous channel user speaks:\n"
            "• Type any message in group\n"
            "• Bot will auto-detect and ban them\n"
            "• They will be removed from VC instantly\n\n"
            "📢 Admin: Use /scan to check for anonymous users."
        )
        await context.bot.send_message(
            chat.id,
            msg,
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )
        
        # Admins scan karo anonymous status ke liye
        await _scan_admins(update, context)
        
    except Exception as e:
        logger.error(f"Error handling VC start: {e}")


async def handle_voice_chat_ended(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Voice chat end hone par log karo"""
    chat = update.effective_chat
    logger.info(f"🎙️ Voice Chat ended in: {getattr(chat, 'title', chat.id)}")


# ============================================================================
# HANDLER 5: ABUSE DETECTION
# ============================================================================

async def handle_text_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Normal text messages handle karo.
    Abuse check karo aur anonymous detection bhi.
    """
    message = update.message
    if not message or not message.text:
        return
    
    # Abuse check
    if contains_abuse(message.text):
        logger.info(f"🤬 Abuse detected from user {message.from_user.id}")
        
        if DELETE_ABUSE_MESSAGES:
            await safe_delete_message(context, message.chat.id, message.message_id)
        
        # User ko temporarily restrict karo (30 min mute)
        try:
            until_date = datetime.now() + timedelta(minutes=30)
            await context.bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                until_date=until_date,
                permissions={
                    "can_send_messages": False,
                    "can_send_media_messages": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False,
                },
            )
            
            warn_msg = (
                f"⚠️ <b>Abuse Detected & Action Taken</b>\n\n"
                f"👤 User: {message.from_user.mention_html()}\n"
                f"🔇 Muted for: <b>30 minutes</b>\n\n"
                f"Gali galoj group mein allowed nahi hai."
            )
            await context.bot.send_message(
                message.chat.id,
                warn_msg,
                parse_mode="HTML",
                reply_markup=support_links_keyboard(),
            )
            logger.info(f"🔇 Muted user {message.from_user.id} for abuse")
            
        except Exception as e:
            logger.error(f"Could not mute user: {e}")


# ============================================================================
# CALLBACK QUERY HANDLER (Colorful Buttons)
# ============================================================================

async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    🌈 Handle all inline button callbacks
    """
    query = update.callback_query
    callback_data = query.data
    user_id = query.from_user.id
    
    # Force join check callback
    if callback_data.startswith("check_join_"):
        await handle_force_join_callback(update, context)
        return
    
    # Menu buttons
    if callback_data == "menu_stats":
        total = banned_count.get(query.message.chat.id, 0)
        stats_text = (
            f"📊 <b>Ban Statistics</b>\n\n"
            f"🚫 Total Bans (this session): <b>{total}</b>\n"
            f"⏰ Running since: Bot start\n\n"
            f"📢 Support: {SUPPORT_CHANNEL_LINK}"
        )
        await query.answer("📊 Showing stats!")
        try:
            await query.edit_message_text(
                stats_text,
                parse_mode="HTML",
                reply_markup=colorful_menu_keyboard(),
            )
        except BadRequest:
            pass
        return
    
    if callback_data == "menu_help":
        help_text = (
            "📖 <b>VC Ban Bot - Help</b>\n\n"
            "<b>🎙️ VC Protection Kaise Kaam Karti Hai:</b>\n"
            "Telegram Bot API directly VC participants list nahi deta.\n"
            "Lekin jab anonymous user group se ban hota hai,\n"
            "woh <u>automatically VC se bhi kick ho jata hai</u>!\n\n"
            "<b>🛡️ Protection Layers:</b>\n"
            "1. Anonymous text message → Instant Ban\n"
            "2. New member anonymous join → Instant Ban\n"
            "3. Abuse in messages → 30 min Mute\n"
            "4. VC start hone par → Auto Alert\n"
            "5. /scan command → Manual anonymous user scan\n"
            "6. 🎯 Force Join → Bot use karne ke liye mandatory\n\n"
            "<b>Commands:</b>\n"
            "/start - Bot activate\n"
            "/help - Ye message\n"
            "/scan - Anonymous users scan karo\n"
            "/stats - Statistics dekho\n"
            "/test - Test bot permissions\n\n"
            "<b>Setup Checklist:</b>\n"
            "✅ Bot ko admin banao\n"
            "✅ 'Ban Users' right do\n"
            "✅ @BotFather se Group Privacy OFF karo"
        )
        await query.answer("📖 Showing help!")
        try:
            await query.edit_message_text(
                help_text,
                parse_mode="HTML",
                reply_markup=colorful_menu_keyboard(),
            )
        except BadRequest:
            pass
        return
    
    if callback_data == "menu_scan":
        await query.answer("🔍 Use /scan in a group to scan!")
        try:
            await query.edit_message_text(
                f"🔍 <b>Scan Command</b>\n\n"
                f"Scan command groups mein kaam karta hai!\n\n"
                f"👮 Admins check karta hai\n"
                f"🎭 Anonymous status detect karta hai\n\n"
                f"💬 Support Group: {SUPPORT_GROUP_LINK}",
                parse_mode="HTML",
                reply_markup=colorful_menu_keyboard(),
            )
        except BadRequest:
            pass
        return
    
    if callback_data == "menu_test":
        await query.answer("🤖 Bot is running perfectly!")
        try:
            await query.edit_message_text(
                f"🤖 <b>Bot Status</b>\n\n"
                f"✅ Bot is online and running!\n"
                f"🛡️ All protection layers active\n\n"
                f"📢 Channel: {SUPPORT_CHANNEL_LINK}\n"
                f"💬 Group: {SUPPORT_GROUP_LINK}",
                parse_mode="HTML",
                reply_markup=colorful_menu_keyboard(),
            )
        except BadRequest:
            pass
        return
    
    # Default: acknowledge the callback
    await query.answer("✅ Button clicked!")


# ============================================================================
# COMMANDS
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start command - with Force Join Check"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        # 🎯 FORCE JOIN CHECK (Sirf private chat mein)
        if FORCE_JOIN_ENABLED:
            passed = await check_force_join(update, context, user.id)
            if not passed:
                return  # User ne join nahi kiya, message bhej diya check_force_join ne
        
        # ✅ User ne force join pass kar liya - welcome message
        await update.message.reply_text(
            f"🔒 <b>VC Ban Bot - Complete Protection</b>\n\n"
            f"🎉 Welcome {user.mention_html()}!\n\n"
            f"<b>🛡️ Features:</b>\n"
            f"• Anonymous channel users → Auto Ban\n"
            f"• Anonymous joiners → Auto Ban\n"
            f"• Abuse detection → Auto Mute\n"
            f"• 🎯 Force Join System → Active\n"
            f"• 🎙️ Voice Chat protection → Active\n\n"
            f"<b>📱 Menu:</b>",
            parse_mode="HTML",
            reply_markup=colorful_menu_keyboard(),
        )
    else:
        # Group mein simple welcome
        await update.message.reply_text(
            f"✅ <b>VC Ban Bot is ACTIVE!</b>\n\n"
            f"Anonymous users will be banned automatically.\n"
            f"Use /help for more info.\n\n"
            f"📢 Support: {SUPPORT_CHANNEL_LINK}",
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help command with colorful buttons"""
    help_text = (
        f"📖 <b>VC Ban Bot - Help</b>\n\n"
        f"<b>🎙️ VC Protection Kaise Kaam Karti Hai:</b>\n"
        f"Telegram Bot API directly VC participants list nahi deta.\n"
        f"Lekin jab anonymous user group se ban hota hai,\n"
        f"woh <u>automatically VC se bhi kick ho jata hai</u>!\n\n"
        f"<b>🛡️ Protection Layers:</b>\n"
        f"1. Anonymous text message → Instant Ban\n"
        f"2. New member anonymous join → Instant Ban\n"
        f"3. Abuse in messages → 30 min Mute\n"
        f"4. VC start hone par → Auto Alert\n"
        f"5. /scan command → Manual anonymous user scan\n"
        f"6. 🎯 Force Join → Bot use karne ke liye mandatory\n\n"
        f"<b>Commands:</b>\n"
        f"/start - Bot activate\n"
        f"/help - Ye message\n"
        f"/scan - Anonymous users scan karo\n"
        f"/stats - Statistics dekho\n"
        f"/test - Test bot permissions\n\n"
        f"<b>Setup Checklist:</b>\n"
        f"✅ Bot ko admin banao\n"
        f"✅ 'Ban Users' right do\n"
        f"✅ @BotFather se Group Privacy OFF karo"
    )
    await update.message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=support_links_keyboard(),
    )


async def _scan_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scan administrators for anonymous status"""
    chat_id = update.effective_chat.id
    
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        
        anonymous_admins = []
        for admin in admins:
            if admin.is_anonymous and admin.status != "creator":
                anonymous_admins.append(admin)
        
        if anonymous_admins:
            msg = (
                f"⚠️ <b>Found {len(anonymous_admins)} Anonymous Admin(s):</b>\n\n"
            )
            for admin in anonymous_admins:
                user = admin.user
                msg += f"• {user.mention_html()} (ID: <code>{user.id}</code>)\n"
            
            msg += (
                f"\n<i>Note: Admins ko auto-ban nahi kar sakte.\n"
                f"Unhe manually anonymous mode off karne ko bolo.</i>\n\n"
                f"📢 Support: {SUPPORT_CHANNEL_LINK}"
            )
            
            await context.bot.send_message(
                chat_id,
                msg,
                parse_mode="HTML",
                reply_markup=support_links_keyboard(),
            )
        else:
            logger.info("✅ No anonymous admins found")
            
    except Exception as e:
        logger.error(f"Error scanning admins: {e}")


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /scan command - Scan for anonymous users in the group.
    
    Note: Bot API all members list nahi deta (Telegram limitation).
    Lekin admins scan kar sakte hain anonymous status ke liye.
    """
    chat_id = update.effective_chat.id
    
    # Show scanning message
    scan_msg = await update.message.reply_text(
        f"🔍 <b>Scanning for anonymous users...</b>",
        parse_mode="HTML",
    )
    
    try:
        # Scan 1: Admins for anonymous status
        admins = await context.bot.get_chat_administrators(chat_id)
        
        anonymous_found = []
        for admin in admins:
            if admin.is_anonymous:
                anonymous_found.append(f"@{admin.user.username}" if admin.user.username else admin.user.full_name)
        
        # Scan 2: Recent joiners check (via get_chat_member for suspicious users)
        # Bot API doesn't provide member list, so we rely on detection handlers
        
        # Build report
        report = (
            f"📊 <b>Scan Report</b>\n\n"
            f"👮 Total Admins: {len(admins)}\n"
            f"🎭 Anonymous Admins: {len(anonymous_found)}\n"
        )
        
        if anonymous_found:
            report += f"\n⚠️ Anonymous Admins: {', '.join(anonymous_found)}\n"
            report += f"<i>(Admins ko manually handle karna padega)</i>\n"
        
        # Total bans count
        total_bans = banned_count.get(chat_id, 0)
        report += f"\n🚫 Total Bans (this session): {total_bans}\n\n"
        
        report += (
            f"<b>Active Protection:</b>\n"
            f"✅ Text anonymous detection → Active\n"
            f"✅ Join detection → Active\n"
            f"✅ Abuse filter → Active\n"
            f"✅ VC auto-alert → Active\n"
            f"✅ Force Join System → Active\n\n"
            f"<i>Bot real-time detection par kaam raha hai.\n"
            f"/scan sirf snapshot hai.</i>\n\n"
            f"📢 Support: {SUPPORT_CHANNEL_LINK}"
        )
        
        await scan_msg.edit_text(
            report,
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )
        
    except Exception as e:
        logger.error(f"Error in scan: {e}")
        await scan_msg.edit_text(
            f"❌ Scan failed: {str(e)}\n\n"
            f"Make sure bot has admin rights.\n\n"
            f"📢 Support: {SUPPORT_CHANNEL_LINK}",
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats command - Show ban statistics with colorful buttons"""
    chat_id = update.effective_chat.id
    total = banned_count.get(chat_id, 0)
    
    stats_text = (
        f"📊 <b>Ban Statistics</b>\n\n"
        f"🚫 Total Bans (this session): <b>{total}</b>\n"
        f"⏰ Running since: Bot start\n\n"
        f"<b>Detection Methods:</b>\n"
        f"• Text message (sender_chat)\n"
        f"• New member join\n"
        f"• Anonymous status change\n\n"
        f"<i>Ye stats bot restart hone par reset hoti hain.</i>\n\n"
        f"📢 Support: {SUPPORT_CHANNEL_LINK}"
    )
    await update.message.reply_text(
        stats_text,
        parse_mode="HTML",
        reply_markup=support_links_keyboard(),
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/test command - Test bot permissions with colorful buttons"""
    chat_id = update.effective_chat.id
    
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        perms = []
        if bot_member.status == "administrator":
            perms.append(f"Status: ✅ Administrator")
            perms.append(f"Ban Users: {'✅ Yes' if bot_member.can_restrict_members else '❌ No'}")
            perms.append(f"Delete Messages: {'✅ Yes' if bot_member.can_delete_messages else '❌ No'}")
            perms.append(f"Pin Messages: {'✅ Yes' if bot_member.can_pin_messages else '❌ No'}")
            perms.append(f"Manage VC: {'✅ Yes' if getattr(bot_member, 'can_manage_video_chats', False) else '❌ No'}")
        else:
            perms.append(f"Status: ❌ {bot_member.status}")
        
        result = "🤖 <b>Bot Permission Test</b>\n\n" + "\n".join(perms)
        
        if bot_member.can_restrict_members:
            result += (
                f"\n\n✅ <b>Bot is properly configured!</b>\n\n"
                f"📢 Support: {SUPPORT_CHANNEL_LINK}\n"
                f"💬 Help: {SUPPORT_GROUP_LINK}"
            )
        else:
            result += (
                f"\n\n⚠️ <b>Bot needs 'Ban Users' permission!</b>\n\n"
                f"📢 Support: {SUPPORT_CHANNEL_LINK}\n"
                f"💬 Help: {SUPPORT_GROUP_LINK}"
            )
        
        await update.message.reply_text(
            result,
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Test failed: {str(e)}\n\n"
            f"📢 Support: {SUPPORT_CHANNEL_LINK}\n"
            f"💬 Help: {SUPPORT_GROUP_LINK}",
            parse_mode="HTML",
            reply_markup=support_links_keyboard(),
        )


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler"""
    logger.error(f"Update {update} caused error: {context.error}")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Start the bot"""
    
    # Validate token
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("=" * 60)
        print("❌ ERROR: Bot token configure nahi hua!")
        print("=" * 60)
        print("\nSteps:")
        print("1. @BotFather (https://t.me/BotFather) par jao")
        print("2. /newbot se naya bot banao")
        print("3. Token copy karo")
        print("4. Is file mein BOT_TOKEN variable mein paste karo")
        print("\nExample:")
        print('    BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"')
        print("=" * 60)
        print("\n🎯 FORCE JOIN SETUP:")
        print("━━━━━━━━━━━━━━━━━━━━")
        print("1. Apna channel aur group ka ID daalo")
        print("2. Bot ko dono mein admin banao")
        print("3. Bot ko 'Add Members' permission do")
        return
    
    print("=" * 60)
    print("🔒 VC Ban Bot (Premium Auto-Ban Edition) Starting...")
    print("=" * 60)
    print(f"🎯 Force Join: {'ENABLED' if FORCE_JOIN_ENABLED else 'DISABLED'}")
    print(f"🔴 Channel: {SUPPORT_CHANNEL_LINK}")
    print(f"🟢 Group: {SUPPORT_GROUP_LINK}")
    print("⚡ NEW: Premium users → Channel msg → INSTANT BAN")
    print("=" * 60)
    
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ========================================================================
    # COMMAND HANDLERS
    # ========================================================================
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("scan", cmd_scan))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("test", cmd_test))
    
    # ========================================================================
    # CALLBACK QUERY HANDLER (Colorful Buttons)
    # ========================================================================
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # ========================================================================
    # MESSAGE HANDLERS (Priority order matters!)
    # ========================================================================
    
    # Handler 1: Anonymous channel messages (HIGHEST priority)
    # filters.SenderChat.CHANNEL catches messages sent via channel identity
    application.add_handler(
        MessageHandler(
            filters.SenderChat.CHANNEL & filters.ChatType.GROUPS,
            handle_anonymous_message,
        )
    )
    
    # Handler 2: Regular text messages (abuse detection)
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_text_message,
        )
    )
    
    # ========================================================================
    # CHAT MEMBER HANDLERS
    # ========================================================================
    
    # When other members' status changes (join/leave/promote)
    application.add_handler(
        ChatMemberHandler(handle_chat_member, ChatMemberHandler.CHAT_MEMBER)
    )
    
    # When bot's own status changes
    application.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    
    # ========================================================================
    # VOICE CHAT HANDLERS
    # ========================================================================
    
    # Voice chat started
    application.add_handler(
        ChatMemberHandler(handle_voice_chat_started, ChatMemberHandler.CHAT_MEMBER)
    )

    application.add_handler(
        ChatMemberHandler(handle_voice_chat_ended, ChatMemberHandler.CHAT_MEMBER)
    )

    # ========================================================================
    # ERROR HANDLER
    # ========================================================================
    application.add_error_handler(error_handler)
    print("✅ All handlers registered!")
    print("🛡️ Protection Layers:")
    print("   • 🚨 Premium user channel msg → AUTO BAN ✅")
    print("   • Anonymous text detection → ACTIVE")
    print("   • Anonymous join detection → ACTIVE")
    print("   • Abuse detection → ACTIVE")
    print("   • VC event monitoring → ACTIVE")
    print("   • 🎯 Force Join System → ACTIVE")
    print("   • 🌈 Colorful Buttons → ACTIVE")
    print("=" * 60)
    print("Bot running... Press Ctrl+C to stop.")
    print("=" * 60)
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
