#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║         TELEGRAM VOICE CHAT ANONYMOUS USER BAN BOT                   ║
║             (Text + Voice Chat Protection)                          ║
╚══════════════════════════════════════════════════════════════════════╝

YE BOT KARTA KYA HAI:
━━━━━━━━━━━━━━━━━━━
1. Voice Chat mein anonymous (channel ID se) aane wale users detect karta hai
2. Unhe VC se kick/mute karta hai - real account pe ban lagata hai
3. Group mein text messages se bhi anonymous users ko ban karta hai
4. VC mein abusive users ke against auto-moderation karta hai

TECHNOLOGY:
━━━━━━━━━━━━
- Telethon (MTProto API) - Telegram ke internal protocol se baat karta hai
- python-telegram-bot - Text message handling ke liye
- Async/await based - Fast aur reliable
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from telethon import TelegramClient, events
from telethon.errors import (
    ChatAdminRequiredError,
    UserAdminInvalidError,
    UserIdInvalidError,
    ChannelPrivateError,
)
from telethon.tl.functions.channels import (
    GetParticipantRequest,
    EditBannedRequest,
    GetFullChannelRequest,
)
from telethon.tl.functions.phone import (
    GetGroupCallRequest,
    EditGroupCallParticipantRequest,
    GetGroupParticipantsRequest,
)
from telethon.tl.types import (
    Channel,
    ChannelParticipant,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChannelParticipantBanned,
    ChannelParticipantLeft,
    ChatBannedRights,
    DataJSON,
    InputPeerChannel,
    InputGroupCall,
    GroupCall,
    GroupCallDiscarded,
    PeerChannel,
    PeerUser,
    UpdateChannelParticipant,
    UpdateNewChannelMessage,
    GroupCallParticipant,
)
from telethon.tl.types.channels import ChannelParticipants

# ============================================================================
# CONFIGURATION - Environment Variables se load hoga
# ============================================================================

# --- Telegram API Credentials ---
API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SESSION_NAME = "vc_ban_session"

# --- Group Configuration ---
_group_id_str = os.environ.get("TELEGRAM_GROUP_ID", "0")
GROUP_ID = int(_group_id_str) if _group_id_str else 0

# --- Ban Settings ---
BAN_ANONYMOUS_VC = True      # VC mein anonymous users ko kick kare?
BAN_ANONYMOUS_TEXT = True    # Text mein anonymous users ko ban kare?
AUTO_MUTE_DURATION = 0       # Auto-mute minutes (0 = permanent until unmute)
DELETE_ABUSIVE_MESSAGES = True  # Anonymous user ke messages delete kare?

# --- Abuse Keywords ---
ABUSE_KEYWORDS = [
    "gali", "gaali", "mc", "bc", "madarchod", "behenchod",
    "chutiya", "chutiye", "randi", "randwe", "bhenchod",
    "bhosdike", "laude", "lund", "gandu", "kutta", "kamine",
    "suar", "harami", "chakka", " hijda ", "namard",
    "bhosdi", "lavde", "tatte", "choot", "bur",
    "fuck", "fuk", "shit", "bitch", "bastard", "asshole",
    "motherfucker", "fatherfucker", "cunt", "dick", "pussy",
    "cock", "nigga", "nigger", "whore", "slut",
]

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VCBanBot")

# ============================================================================
# BAN TRACKING (Duplicate ban avoid karne ke liye)
# ============================================================================
recently_banned: Set[int] = set()
ban_cooldown = timedelta(minutes=5)
last_ban_time: Dict[int, datetime] = {}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_recently_banned(user_id: int) -> bool:
    """Check kare ki user recently banned toh nahi (duplicate se bachne ke liye)"""
    if user_id in last_ban_time:
        if datetime.now() - last_ban_time[user_id] < ban_cooldown:
            return True
    return False


def mark_banned(user_id: int):
    """User ko banned list mein daalo"""
    last_ban_time[user_id] = datetime.now()
    recently_banned.add(user_id)
    asyncio.create_task(_remove_from_cooldown(user_id))


async def _remove_from_cooldown(user_id: int):
    """Cooldown period ke baad user ID hatao"""
    await asyncio.sleep(300)  # 5 minutes
    recently_banned.discard(user_id)


# ============================================================================
# MAIN BOT CLASS
# ============================================================================

class VCBanBot:
    """Telegram Voice Chat + Text Anonymous User Ban Bot"""

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.group_entity: Optional[Channel] = None
        self.group_call: Optional[GroupCall] = None
        self.active_vcs: Dict[int, GroupCall] = {}
        self.vc_participants: Dict[int, Set[int]] = {}

    async def start(self):
        """Bot start karo aur initialize karo"""
        if API_ID == 0 or not API_HASH or not BOT_TOKEN:
            logger.error("❌ CONFIGURATION MISSING!")
            logger.error("=" * 60)
            logger.error("Required environment variables set nahi hue:")
            logger.error("  TELEGRAM_API_ID   - my.telegram.org se lo")
            logger.error("  TELEGRAM_API_HASH  - my.telegram.org se lo")
            logger.error("  TELEGRAM_BOT_TOKEN - @BotFather se lo")
            logger.error("  TELEGRAM_GROUP_ID  - Group ka numeric ID")
            logger.error("=" * 60)
            sys.exit(1)

        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

        try:
            await self.client.start(bot_token=BOT_TOKEN)
            logger.info("✅ Bot connected to Telegram!")
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            sys.exit(1)

        if GROUP_ID != 0:
            try:
                self.group_entity = await self.client.get_entity(GROUP_ID)
                logger.info(f"✅ Group loaded: {self.group_entity.title}")
            except Exception as e:
                logger.warning(f"⚠️ Could not load group {GROUP_ID}: {e}")
                logger.info("Bot will work with any group he's admin in.")

        await self._setup_handlers()

        if self.group_entity:
            await self._scan_voice_chat(self.group_entity)
        else:
            logger.info("ℹ️ Group entity not loaded yet — will scan VC on first message from group")

        # Launch periodic VC scan as background task
        asyncio.create_task(self.periodic_vc_scan())
        logger.info("✅ Periodic VC scanner started (every 30s)")

        logger.info("=" * 60)
        logger.info("🔒 VCBanBot ACTIVE & PROTECTING!")
        logger.info("=" * 60)
        logger.info("Bot ab active hai aur:")
        logger.info("  • VC mein anonymous users detect karega")
        logger.info("  • Text mein anonymous users ban karega")
        logger.info("  • Abusive messages delete karega")
        logger.info("  • Invite link / channel ID se join karne wale ko ban karega")
        logger.info("  • VC mein aaye to wahan se bhi kick karega")
        logger.info("=" * 60)

        await self.client.run_until_disconnected()

    async def _setup_handlers(self):
        """Saare event handlers setup karo"""

        @self.client.on(events.Raw)
        async def handle_raw_update(event):
            await self._handle_voice_chat_updates(event)

        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self._handle_message(event)

        @self.client.on(events.NewMessage(forwards=True))
        async def handle_forwarded_message(event):
            await self._handle_channel_forward(event)

        # ---- HANDLER 4: Group Join Detection ----
        # Fires when any user joins or is added to a group
        @self.client.on(events.ChatAction)
        async def handle_chat_action(event):
            await self._handle_join_action(event)

        logger.info("✅ All event handlers registered")

    # ========================================================================
    # VOICE CHAT PARTICIPANT DETECTION
    # ========================================================================

    async def _handle_voice_chat_updates(self, event):
        """Voice chat related updates handle karo"""
        try:
            if isinstance(event, (UpdateChannelParticipant,)):
                await self._check_participant_join(event)
            elif isinstance(event, UpdateNewChannelMessage):
                msg = event.message
                if hasattr(msg, 'from_id') and msg.from_id is None:
                    if hasattr(msg, 'peer_id'):
                        await self._handle_anonymous_message(msg)
        except Exception as e:
            logger.error(f"Error in raw update handler: {e}")

    async def _check_participant_join(self, event: UpdateChannelParticipant):
        """UpdateChannelParticipant: detect channel-ID joins and invite-link joins"""
        try:
            new_p = event.new_participant
            prev_p = event.prev_participant

            # Only act on new joins (prev was absent/banned/left)
            is_new_join = (
                prev_p is None
                or isinstance(prev_p, (ChannelParticipantBanned, ChannelParticipantLeft))
            )
            if not is_new_join:
                return

            # Ignore if the new state is not an active membership
            if new_p is None or isinstance(new_p, (ChannelParticipantBanned, ChannelParticipantLeft)):
                return

            user_id = event.user_id
            channel_id = event.channel_id
            invite = event.invite  # None if joined via public link / username search

            # --- Case 1: Joined via invite link (hidden/private link) ---
            if invite is not None:
                link = getattr(invite, 'link', 'hidden')
                logger.warning(
                    f"🔗 User {user_id} joined group {channel_id} via invite link: {link}"
                )
                await self._ban_new_member(
                    user_id=user_id,
                    channel_id=channel_id,
                    reason=f"Invite link join ({link})",
                )
                return

            # --- Case 2: Joined as a channel identity (not a real user) ---
            new_peer = getattr(new_p, 'peer', None)
            if new_peer is not None and isinstance(new_peer, PeerChannel):
                logger.warning(
                    f"📢 Channel peer {new_peer.channel_id} joined group {channel_id}"
                )
                await self._ban_new_member(
                    user_id=user_id,
                    channel_id=channel_id,
                    reason="Channel ID join (not a real user account)",
                )

        except Exception as e:
            logger.error(f"Error in _check_participant_join: {e}")

    async def _handle_join_action(self, event):
        """ChatAction handler: detect user_joined / user_added and check anonymity"""
        try:
            if not (event.user_joined or event.user_added):
                return

            user_id = event.user_id
            if not user_id:
                return

            chat = await event.get_chat()
            chat_id = chat.id

            logger.info(f"👤 User {user_id} joined group {chat_id} (ChatAction)")

            # Check if this user is an anonymous admin or channel-based
            try:
                participant = await self.client(
                    GetParticipantRequest(channel=chat, participant=user_id)
                )
                p = participant.participant

                # Anonymous admin joining
                if isinstance(p, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    if getattr(getattr(p, 'admin_rights', None), 'anonymous', False):
                        logger.warning(f"👤 Anonymous admin {user_id} joined — banning")
                        await self._ban_new_member(
                            user_id=user_id,
                            channel_id=chat_id,
                            reason="Anonymous admin account",
                        )
                        return

                # Channel-peer join
                peer = getattr(p, 'peer', None)
                if peer is not None and isinstance(peer, PeerChannel):
                    logger.warning(f"📢 Channel peer joined as user {user_id} — banning")
                    await self._ban_new_member(
                        user_id=user_id,
                        channel_id=chat_id,
                        reason="Channel ID join (not a real user account)",
                    )

            except (UserIdInvalidError, ChatAdminRequiredError):
                pass
            except Exception as e:
                logger.error(f"Error checking joined user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error in _handle_join_action: {e}")

    async def _kick_from_vc_if_present(self, user_id: int, group_channel_id: int, as_channel_id: Optional[int] = None):
        """User/channel ko VC se kick karo agar present hai.
        
        as_channel_id: agar user VC mein channel identity se hai, woh channel_id daao.
        """
        try:
            group_call = self.active_vcs.get(group_channel_id)
            if group_call is None:
                return

            input_call = InputGroupCall(
                id=group_call.id,
                access_hash=group_call.access_hash,
            )

            # Use PeerChannel if joining as channel, otherwise PeerUser
            if as_channel_id is not None:
                peer = PeerChannel(channel_id=as_channel_id)
                label = f"channel {as_channel_id}"
            else:
                peer = PeerUser(user_id=user_id)
                label = f"user {user_id}"

            await self.client(
                EditGroupCallParticipantRequest(
                    call=input_call,
                    participant=peer,
                    muted=True,
                    video_stopped=True,
                )
            )
            logger.info(f"🎙️ Kicked {label} from VC in group {group_channel_id}")
        except Exception as e:
            logger.error(f"Error kicking from VC: {e}")

    async def _ban_new_member(self, user_id: int, channel_id: int, reason: str):
        """Naye member ko group se ban karo + VC se kick karo"""
        if is_recently_banned(user_id):
            return

        try:
            group = await self.client.get_entity(PeerChannel(channel_id=channel_id))
        except Exception as e:
            logger.error(f"Could not get group entity for {channel_id}: {e}")
            return

        # Step 1: Kick from VC if present
        await self._kick_from_vc_if_present(user_id, channel_id)

        # Step 2: Ban from the group
        rights = ChatBannedRights(
            until_date=None,
            view_messages=True,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
            send_polls=True,
            change_info=True,
            invite_users=True,
            pin_messages=True,
            manage_topics=True,
            send_photos=True,
            send_videos=True,
            send_roundvideos=True,
            send_audios=True,
            send_voices=True,
            send_docs=True,
            send_plain=True,
        )

        ban_ok = False
        try:
            await self.client(
                EditBannedRequest(
                    channel=group,
                    participant=user_id,
                    banned_rights=rights,
                )
            )
            mark_banned(user_id)
            ban_ok = True
            logger.warning(f"🚫 BANNED user {user_id} from group {channel_id} — {reason}")
        except ChatAdminRequiredError:
            logger.error("❌ Bot needs 'Ban Users' admin right!")
        except UserAdminInvalidError:
            logger.warning(f"⚠️ Cannot ban admin user {user_id}")
        except Exception as e:
            logger.error(f"❌ Ban failed for user {user_id}: {e}")

        # Step 3: Notify the group
        try:
            status_icon = "✅" if ban_ok else "⚠️ (failed — check admin rights)"
            notification = (
                f"🚫 **Suspicious Join Detected & Actioned**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"📍 Reason: {reason}\n"
                f"🔨 Banned: {status_icon}\n"
                f"🎙️ VC Kick: ✅ (if in VC)\n"
                f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"_Real account se aao. Hidden links aur channel ID joins allowed nahi hain._"
            )
            await self.client.send_message(channel_id, notification)
        except Exception as e:
            logger.error(f"Error sending join-ban notification: {e}")

    async def _scan_voice_chat(self, group: Channel):
        """Group ki voice chat scan karo aur participants check karo"""
        try:
            full_channel = await self.client(GetFullChannelRequest(channel=group))
            group_call = full_channel.full_chat.call

            if group_call is None:
                logger.info("ℹ️ No active voice chat in this group")
                return

            self.group_call = group_call
            self.active_vcs[group.id] = group_call
            logger.info("🎙️ Voice Chat detected! Scanning participants...")

            input_call = InputGroupCall(id=group_call.id, access_hash=group_call.access_hash)
            participants_obj = await self.client(
                GetGroupParticipantsRequest(
                    call=input_call,
                    ids=[],
                    sources=[],
                    offset="",
                    limit=100,
                )
            )

            participants: List[GroupCallParticipant] = participants_obj.participants
            logger.info(f"👥 Found {len(participants)} VC participants")

            banned_count = 0
            for participant in participants:
                peer = participant.peer

                if isinstance(peer, PeerUser):
                    # Normal user in VC — check if they're anonymous
                    user_id = peer.user_id
                    if not is_recently_banned(user_id):
                        if await self._is_anonymous_in_vc(user_id, group):
                            await self._ban_from_vc(input_call, peer, group)
                            banned_count += 1

                elif isinstance(peer, PeerChannel):
                    # Channel identity in VC — always kick + ban
                    channel_id = peer.channel_id
                    logger.warning(f"📢 Channel {channel_id} detected in VC — kicking")
                    if not is_recently_banned(channel_id):
                        await self._ban_channel_from_vc(input_call, peer, group)
                        banned_count += 1

            if banned_count > 0:
                logger.info(f"🚫 Banned {banned_count} anonymous/channel users from VC")

        except ChatAdminRequiredError:
            logger.error("❌ Bot ko admin rights chahiye VC participants dekhne ke liye")
        except Exception as e:
            logger.error(f"Error scanning VC: {e}")

    async def _is_anonymous_in_vc(self, user_id: int, group: Channel) -> bool:
        """Check kare ki user anonymous channel se VC mein aaya hai"""
        try:
            participant = await self.client(
                GetParticipantRequest(channel=group, participant=user_id)
            )
            p = participant.participant

            if isinstance(p, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                if hasattr(p, 'admin_rights') and p.admin_rights.anonymous:
                    logger.info(f"👤 User {user_id} is anonymous admin in VC")
                    return True

            if hasattr(p, 'peer') and isinstance(p.peer, PeerChannel):
                logger.info(f"📢 User {user_id} joined VC via channel ID!")
                return True

            return False

        except UserIdInvalidError:
            logger.warning(f"⚠️ User {user_id} not found in group")
            return False
        except Exception as e:
            logger.error(f"Error checking participant {user_id}: {e}")
            return False

    def _full_ban_rights(self) -> ChatBannedRights:
        """Return full permanent ban rights"""
        return ChatBannedRights(
            until_date=None,
            view_messages=True,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
            send_polls=True,
            change_info=True,
            invite_users=True,
            pin_messages=True,
            manage_topics=True,
            send_photos=True,
            send_videos=True,
            send_roundvideos=True,
            send_audios=True,
            send_voices=True,
            send_docs=True,
            send_plain=True,
        )

    async def _ban_from_vc(self, input_call: InputGroupCall, peer: PeerUser, group: Channel):
        """User (PeerUser) ko VC se kick karo + group se ban karo"""
        user_id = peer.user_id
        try:
            # Step 1: Kick from VC
            await self.client(
                EditGroupCallParticipantRequest(
                    call=input_call,
                    participant=peer,
                    muted=True,
                    video_stopped=True,
                )
            )
            logger.info(f"🎙️ Kicked user {user_id} from VC")
        except Exception as e:
            logger.error(f"❌ VC kick failed for user {user_id}: {e}")

        try:
            # Step 2: Ban from group
            await self.client(
                EditBannedRequest(
                    channel=group,
                    participant=user_id,
                    banned_rights=self._full_ban_rights(),
                )
            )
            mark_banned(user_id)
            await self._send_ban_notification(group, user_id, "Voice Chat Anonymous User")
            logger.warning(f"🚫 BANNED: User {user_id} from VC + Group (Anonymous)")
        except ChatAdminRequiredError:
            logger.error("❌ Bot needs admin rights to ban users!")
        except UserAdminInvalidError:
            logger.warning(f"⚠️ Cannot ban admin user {user_id}")
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")

    async def _ban_channel_from_vc(self, input_call: InputGroupCall, peer: PeerChannel, group: Channel):
        """Channel identity (PeerChannel) ko VC se kick karo + group se ban karo"""
        channel_id = peer.channel_id
        try:
            # Step 1: Kick channel from VC using PeerChannel (critical fix)
            await self.client(
                EditGroupCallParticipantRequest(
                    call=input_call,
                    participant=peer,
                    muted=True,
                    video_stopped=True,
                )
            )
            logger.info(f"🎙️ Kicked channel {channel_id} from VC")
        except Exception as e:
            logger.error(f"❌ VC kick failed for channel {channel_id}: {e}")

        try:
            # Step 2: Ban channel from group
            await self.client(
                EditBannedRequest(
                    channel=group,
                    participant=peer,
                    banned_rights=self._full_ban_rights(),
                )
            )
            mark_banned(channel_id)
            await self._send_ban_notification(group, channel_id, "VC Channel ID Join")
            logger.warning(f"🚫 BANNED: Channel {channel_id} from VC + Group")
        except ChatAdminRequiredError:
            logger.error("❌ Bot needs admin rights to ban channels!")
        except Exception as e:
            logger.error(f"Error banning channel {channel_id}: {e}")

    # ========================================================================
    # TEXT MESSAGE HANDLING (Anonymous Channel Detection)
    # ========================================================================

    async def _handle_message(self, event):
        """Group mein naya message handle karo"""
        message = event.message

        if not event.is_group and not event.is_channel:
            return

        # Detect anonymous channel posting: from_id is a PeerChannel (not a user)
        if BAN_ANONYMOUS_TEXT:
            from_id = getattr(message, 'from_id', None)
            if isinstance(from_id, PeerChannel):
                logger.info(f"📢 Anonymous channel post detected via PeerChannel: {from_id.channel_id}")
                await self._ban_anonymous_sender_telethon(message, from_id)
                return

        if message.text and DELETE_ABUSIVE_MESSAGES:
            if self._contains_abuse(message.text.lower()):
                await self._handle_abusive_message(message)

    async def _handle_channel_forward(self, event):
        """Channel se forwarded messages handle karo"""
        message = event.message

        if not event.is_group and not event.is_channel:
            return

        if hasattr(message, 'sender_chat') and message.sender_chat:
            chat_type = message.sender_chat.__class__.__name__
            if chat_type == 'Channel':
                channel_id = message.sender_chat.id
                logger.info(
                    f"📢 Anonymous channel message: {message.sender_chat.title} "
                    f"(ID: {channel_id})"
                )
                if BAN_ANONYMOUS_TEXT:
                    await self._ban_anonymous_sender(message)

    async def _ban_anonymous_sender_telethon(self, message, peer_channel: PeerChannel):
        """Telethon layer: anonymous channel sender ko ban + message delete karo"""
        channel_id = peer_channel.channel_id

        if is_recently_banned(channel_id):
            return

        chat = await message.get_chat()
        channel_title = "Unknown"
        try:
            channel_entity = await self.client.get_entity(peer_channel)
            channel_title = getattr(channel_entity, 'title', str(channel_id))
        except Exception:
            pass

        rights = ChatBannedRights(
            until_date=None,
            view_messages=True,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
            send_polls=True,
            change_info=True,
            invite_users=True,
            pin_messages=True,
            manage_topics=True,
            send_photos=True,
            send_videos=True,
            send_roundvideos=True,
            send_audios=True,
            send_voices=True,
            send_docs=True,
            send_plain=True,
        )

        # Step 1: Ban the channel from the group
        ban_ok = False
        try:
            await self.client(
                EditBannedRequest(
                    channel=chat,
                    participant=peer_channel,
                    banned_rights=rights,
                )
            )
            mark_banned(channel_id)
            ban_ok = True
            logger.warning(f"🚫 BANNED channel '{channel_title}' (ID: {channel_id}) from group")
        except ChatAdminRequiredError:
            logger.error("❌ Bot needs 'Ban Users' admin right!")
        except UserAdminInvalidError:
            logger.warning(f"⚠️ Cannot ban admin channel {channel_id}")
        except Exception as e:
            logger.error(f"❌ Ban failed for channel {channel_id}: {e}")

        # Step 2: Kick channel from VC if they're present there
        vc_kicked = False
        try:
            group_call = self.active_vcs.get(chat.id)
            if group_call:
                input_call = InputGroupCall(id=group_call.id, access_hash=group_call.access_hash)
                await self.client(
                    EditGroupCallParticipantRequest(
                        call=input_call,
                        participant=peer_channel,
                        muted=True,
                        video_stopped=True,
                    )
                )
                vc_kicked = True
                logger.warning(f"🎙️ Kicked channel {channel_id} from VC (was abusing in VC)")
        except Exception as e:
            logger.error(f"❌ VC kick failed for channel {channel_id}: {e}")

        # Step 3: Delete the message
        try:
            await message.delete()
            logger.info(f"🗑️ Deleted message from channel {channel_title}")
        except Exception as e:
            logger.error(f"❌ Delete failed: {e}")

        # Step 4: Send notification
        try:
            status_icon = "✅" if ban_ok else "⚠️ (ban failed — check admin rights)"
            vc_icon = "✅ Kicked" if vc_kicked else "➖ Not in VC"
            ban_msg = (
                f"🚫 **Anonymous Channel Detected**\n\n"
                f"📢 Channel: `{channel_title}`\n"
                f"🆔 Channel ID: `{channel_id}`\n"
                f"🔨 Banned from group: {status_icon}\n"
                f"🎙️ VC: {vc_icon}\n"
                f"🗑️ Message: Deleted\n"
                f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"_Real account se aao, anonymous posting allowed nahi hai._"
            )
            await self.client.send_message(chat.id, ban_msg)
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

    async def _ban_anonymous_sender(self, message):
        """Fallback: sender_chat based ban (PTB-style messages in Telethon)"""
        try:
            sender_chat = message.sender_chat
            channel_id = sender_chat.id
            channel_title = sender_chat.title or "Unknown"

            if is_recently_banned(channel_id):
                return

            chat = await message.get_chat()
            peer = PeerChannel(channel_id=channel_id)
            await self._ban_anonymous_sender_telethon(message, peer)

        except Exception as e:
            logger.error(f"Error in _ban_anonymous_sender: {e}")

    async def _handle_anonymous_message(self, message):
        """Anonymous admin message handle karo (from_id is None)"""
        pass

    # ========================================================================
    # ABUSE DETECTION
    # ========================================================================

    def _contains_abuse(self, text: str) -> bool:
        """Check kare ki message mein abuse/gali hai"""
        if not text:
            return False

        text_lower = text.lower()

        for keyword in ABUSE_KEYWORDS:
            if keyword in text_lower:
                return True
            if f" {keyword} " in f" {text_lower} ":
                return True

        return False

    async def _handle_abusive_message(self, message):
        """Abusive message handle karo"""
        try:
            chat = await message.get_chat()
            user_id = message.sender_id

            if DELETE_ABUSIVE_MESSAGES:
                await message.delete()

            if user_id:
                mute_rights = ChatBannedRights(
                    until_date=datetime.now() + timedelta(minutes=30),
                    send_messages=True,
                    send_media=True,
                )

                await self.client(
                    EditBannedRequest(
                        channel=chat,
                        participant=user_id,
                        banned_rights=mute_rights,
                    )
                )

                warn_msg = (
                    f"⚠️ **Abuse Detected & Action Taken**\n\n"
                    f"👤 User ID: `{user_id}`\n"
                    f"🕐 Muted for: 30 minutes\n\n"
                    f"Message containing abuse was deleted.\n"
                    f"Group rules follow karo."
                )

                await self.client.send_message(chat.id, warn_msg)
                logger.info(f"🔇 Muted user {user_id} for 30 min (abuse detected)")

        except Exception as e:
            logger.error(f"Error handling abusive message: {e}")

    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================

    async def _send_ban_notification(self, group, user_id: int, reason: str):
        """Group mein ban notification bhejo"""
        try:
            notification = (
                f"🚫 **User Banned from Voice Chat**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"📍 Source: {reason}\n"
                f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"⚠️ Ye user anonymous channel ID se VC mein aaya tha.\n"
                f"Group rules ke against hai.\n\n"
                f"_Real account se aao, anonymous VC join allowed nahi hai._"
            )
            await self.client.send_message(group.id, notification)
        except Exception as e:
            logger.error(f"Error sending ban notification: {e}")

    async def periodic_vc_scan(self):
        """Har kuch der mein VC scan karo (background task)"""
        while True:
            try:
                await asyncio.sleep(30)

                # Try to load group entity if not loaded yet
                if self.group_entity is None and GROUP_ID != 0:
                    try:
                        self.group_entity = await self.client.get_entity(GROUP_ID)
                        logger.info(f"✅ Group entity loaded (retry): {self.group_entity.title}")
                    except Exception:
                        pass  # Still not reachable, try again next cycle

                if self.group_entity:
                    await self._scan_voice_chat(self.group_entity)

            except Exception as e:
                logger.error(f"Error in periodic scan: {e}")
                await asyncio.sleep(60)


# ============================================================================
# STANDALONE TEXT BOT (python-telegram-bot based backup)
# ============================================================================

from telegram import Update
from telegram.ext import (
    Application as PTBApplication,
    CommandHandler,
    MessageHandler,
    filters as ptb_filters,
    ContextTypes,
)


class TextBanBot:
    """python-telegram-bot based text protection (backup layer)"""

    def __init__(self, token: str):
        self.token = token
        self.app: Optional[PTBApplication] = None

    # Force-join channels — users must be members before using the bot
    FORCE_JOIN_CHANNELS = [
        {"username": "Globall_X",         "url": "https://t.me/Globall_X",         "label": "📢 Support"},
        {"username": "Globall_X_Support", "url": "https://t.me/Globall_X_Support", "label": "💬 Help"},
    ]

    async def _check_force_join(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Return True if user has joined all required channels, False + prompt if not."""
        user = update.effective_user
        if not user:
            return False

        not_joined = []
        for ch in self.FORCE_JOIN_CHANNELS:
            try:
                member = await context.bot.get_chat_member(
                    chat_id=f"@{ch['username']}", user_id=user.id
                )
                if member.status in ("left", "kicked", "banned"):
                    not_joined.append(ch)
            except Exception:
                not_joined.append(ch)

        if not not_joined:
            return True

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [InlineKeyboardButton(ch["label"], url=ch["url"])]
            for ch in not_joined
        ]
        buttons.append([InlineKeyboardButton("✅ I've Joined — Try Again", callback_data="check_join")])

        await update.message.reply_text(
            "⚠️ *Access Restricted*\n\n"
            "You must join our channels before using this bot\\.\n\n"
            "👇 Click the buttons below to join, then press *I've Joined*\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return False

    async def start(self):
        """Start the text protection bot"""
        from telegram.ext import CallbackQueryHandler
        self.app = PTBApplication.builder().token(self.token).build()

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("vcscan", self.cmd_vcscan))
        self.app.add_handler(CallbackQueryHandler(self.handle_join_check, pattern="^check_join$"))

        self.app.add_handler(
            MessageHandler(
                ptb_filters.ChatType.GROUPS & ptb_filters.SenderChat.CHANNEL,
                self.handle_anonymous_channel,
            )
        )

        logger.info("✅ TextBanBot (backup layer) started")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def handle_join_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'I've Joined' button — re-check membership."""
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        not_joined = []
        for ch in self.FORCE_JOIN_CHANNELS:
            try:
                member = await context.bot.get_chat_member(
                    chat_id=f"@{ch['username']}", user_id=user.id
                )
                if member.status in ("left", "kicked", "banned"):
                    not_joined.append(ch)
            except Exception:
                not_joined.append(ch)

        if not not_joined:
            await query.edit_message_text(
                "✅ *Access Granted!*\n\nThank you for joining\\. You can now use the bot\\.\nSend /start to get started\\.",
                parse_mode="MarkdownV2",
            )
        else:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            buttons = [
                [InlineKeyboardButton(ch["label"], url=ch["url"])]
                for ch in not_joined
            ]
            buttons.append([InlineKeyboardButton("✅ I've Joined — Try Again", callback_data="check_join")])
            await query.edit_message_text(
                "❌ *Still not joined*\n\nPlease join all channels below and try again\\.",
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start command"""
        if not await self._check_force_join(update, context):
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Support Channel", url="https://t.me/Globall_X")],
            [InlineKeyboardButton("💬 Help Group",      url="https://t.me/Globall_X_Support")],
        ])

        await update.message.reply_text(
            "🔒 *Welcome to VC Guard Bot*\n\n"
            "I protect your Telegram group from anonymous users and abusers\\.\n\n"
            "🛡️ *What I do:*\n"
            "• Ban anonymous channel IDs from Voice Chat\n"
            "• Kick \\+ ban channel\\-ID users from VC instantly\n"
            "• Delete messages from anonymous senders\n"
            "• Detect and mute abusive language \\(30 min\\)\n"
            "• Block users who join via hidden invite links\n"
            "• Periodic VC scan every 30 seconds\n\n"
            "⚙️ *Setup:*\n"
            "1\\. Add me to your group\n"
            "2\\. Make me Admin with *Ban Users* permission\n"
            "3\\. That's it — I'll handle the rest\\!\n\n"
            "📢 Support: @Globall\\_X\n"
            "💬 Help: @Globall\\_X\\_Support\n\n"
            "👉 For help use /help",
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/help command"""
        if not await self._check_force_join(update, context):
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Support", url="https://t.me/Globall_X"),
             InlineKeyboardButton("💬 Help",    url="https://t.me/Globall_X_Support")],
        ])

        help_text = (
            "📖 *VC Guard Bot — Help*\n\n"
            "📌 *Commands:*\n"
            "/start \\- Welcome message \\& bot info\n"
            "/help \\- This help message\n"
            "/status \\- Check bot permissions in this group\n"
            "/vcscan \\- Manually trigger a Voice Chat scan\n\n"
            "🛡️ *Features:*\n"
            "• Auto\\-ban anonymous VC users \\(channel ID\\)\n"
            "• Auto\\-ban anonymous text message senders\n"
            "• Abuse keyword detection \\+ 30\\-min mute\n"
            "• Block invite\\-link / hidden\\-link joins\n"
            "• Periodic VC scan every 30 seconds\n\n"
            "⚙️ *Required Admin Rights:*\n"
            "• Ban Users ✅\n"
            "• Delete Messages ✅\n"
            "• Manage Voice Chats ✅\n\n"
            "📢 Support: @Globall\\_X\n"
            "💬 Help: @Globall\\_X\\_Support"
        )
        await update.message.reply_text(help_text, parse_mode="MarkdownV2", reply_markup=keyboard)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status command"""
        if not await self._check_force_join(update, context):
            return

        chat = update.effective_chat
        try:
            bot_member = await chat.get_member(context.bot.id)
            can_restrict = getattr(bot_member, "can_restrict_members", False)
            can_delete   = getattr(bot_member, "can_delete_messages", False)
            can_vc       = getattr(bot_member, "can_manage_voice_chats", False) or \
                           getattr(bot_member, "can_manage_video_chats", False)
        except Exception:
            can_restrict = can_delete = can_vc = False

        def icon(v): return "✅" if v else "❌"

        status = (
            f"🤖 *Bot Status*\n\n"
            f"Ban Users: {icon(can_restrict)}\n"
            f"Delete Messages: {icon(can_delete)}\n"
            f"Manage Voice Chat: {icon(can_vc)}\n\n"
            f"Overall Protection: {'✅ Active' if can_restrict else '⚠️ Needs admin rights'}\n\n"
            f"📢 @Globall\\_X \\| 💬 @Globall\\_X\\_Support"
        )
        await update.message.reply_text(status, parse_mode="MarkdownV2")

    async def cmd_vcscan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/vcscan command"""
        if not await self._check_force_join(update, context):
            return

        await update.message.reply_text(
            "🎙️ *Voice Chat Scan Triggered*\n\n"
            "Scanning all VC participants for anonymous channel IDs\\.\\.\\.\n"
            "Results will appear in the group if any violators are found\\.\n\n"
            "📢 @Globall\\_X \\| 💬 @Globall\\_X\\_Support",
            parse_mode="MarkdownV2",
        )

    async def handle_anonymous_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """python-telegram-bot se anonymous channel message handle karo"""
        message = update.message
        chat = update.effective_chat

        if not message or not message.sender_chat:
            return

        sender_chat = message.sender_chat
        channel_id = sender_chat.id
        channel_title = sender_chat.title or "Unknown"

        logger.info(f"📢 (PTB) Anonymous channel detected: {channel_title} (ID: {channel_id})")

        # Step 1: Ban the sender channel
        ban_ok = False
        try:
            await context.bot.ban_chat_sender_chat(
                chat_id=chat.id,
                sender_chat_id=channel_id,
            )
            ban_ok = True
            logger.warning(f"🚫 (PTB) Banned channel '{channel_title}' (ID: {channel_id})")
        except Exception as e:
            logger.error(f"❌ (PTB) Ban failed for channel {channel_id}: {e}")

        # Step 2: Delete the message
        try:
            await message.delete()
            logger.info(f"🗑️ (PTB) Deleted message from channel {channel_title}")
        except Exception as e:
            logger.error(f"❌ (PTB) Delete failed: {e}")

        # Step 3: Send notification
        try:
            status_icon = "✅" if ban_ok else "⚠️ (ban failed — check admin rights)"
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"🚫 *Anonymous Channel Detected*\n\n"
                    f"📢 Channel: `{channel_title}`\n"
                    f"🆔 ID: `{channel_id}`\n"
                    f"🔨 Banned: {status_icon}\n"
                    f"🗑️ Message: Deleted\n\n"
                    f"_Real account se aao, anonymous posting allowed nahi hai\\._"
                ),
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"❌ (PTB) Notification failed: {e}")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main function - dono layers start karo"""
    logger.info("=" * 60)
    logger.info("🔒 Starting Telegram VC + Text Ban Bot")
    logger.info("=" * 60)

    tasks = []
    vc_bot = VCBanBot()

    text_bot = None
    if BOT_TOKEN:
        text_bot = TextBanBot(BOT_TOKEN)

    if text_bot:
        tasks.append(asyncio.create_task(text_bot.start()))

    try:
        await vc_bot.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Bot stopped by user")
    finally:
        if vc_bot.client:
            await vc_bot.client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
