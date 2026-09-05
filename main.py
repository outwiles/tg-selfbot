import asyncio
import os
import time
import threading
from flask import Flask
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.errors import ChatAdminRequiredError, UserIsBlockedError
from telethon.tl.types import User
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
COMMAND_PREFIX = "."
BROADCAST_DELAY_SECONDS = 3
BROADCAST_CONFIRM_WINDOW = 30
PORT = int(os.environ.get("PORT", 8080))
app = Flask(__name__)
@app.route("/")
def home():
    return "OK", 200
@app.route("/health")
def health():
    return {"status": "ok"}, 200
def run_flask():
    app.run(host="0.0.0.0", port=PORT)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
last_error = None
pending_broadcast = {}
async def get_reply_message(event):
    if not event.is_reply:
        return None
    return await event.get_reply_message()
def record_error(e):
    global last_error
    last_error = str(e)
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}dm(?:\s+(.+))?$"))
async def cmd_dm(event):
    try:
        text = event.pattern_match.group(1)
        reply = await get_reply_message(event)
        if not reply or not text:
            await event.edit("Usage: reply to a message with `.dm <text>`")
            return
        sender = await reply.get_sender()
        if not isinstance(sender, User):
            await event.edit(".dm only works replying to a message from a user.")
            return
        await client.send_message(sender.id, text)
        await event.edit(f"DM sent to {sender.first_name or sender.id}.")
    except UserIsBlockedError:
        await event.edit("That user has blocked you.")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}block$"))
async def cmd_block(event):
    try:
        reply = await get_reply_message(event)
        if not reply:
            await event.edit("Usage: reply to the user's message with `.block`")
            return
        sender = await reply.get_sender()
        if not isinstance(sender, User):
            await event.edit(".block only works on a user's message.")
            return
        await client(functions.contacts.BlockRequest(id=sender.id))
        await event.edit(f"Blocked {sender.first_name or sender.id}.")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}fd\s+(\S+)$"))
async def cmd_fd(event):
    try:
        target = event.pattern_match.group(1).lstrip("@")
        reply = await get_reply_message(event)
        if not reply:
            await event.edit("Usage: reply to a message with `.fd <username>`")
            return
        entity = await client.get_entity(target)
        await client.forward_messages(entity, reply)
        await event.edit(f"Forwarded to @{target}.")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}fdc\s+(\S+)$"))
async def cmd_fdc(event):
    try:
        link = event.pattern_match.group(1)
        reply = await get_reply_message(event)
        if not reply:
            await event.edit("Usage: reply to a message with `.fdc <link>`")
            return
        entity = await client.get_entity(link)
        await client.forward_messages(entity, reply)
        await event.edit("Forwarded to channel/group.")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}bdc(\s+confirm)?$"))
async def cmd_bdc(event):
    chat_id = event.chat_id
    confirm = bool(event.pattern_match.group(1))
    try:
        if not confirm:
            reply = await get_reply_message(event)
            if not reply or not reply.raw_text:
                await event.edit(f"Usage: reply to a text message with `.bdc`, then confirm with `.bdc confirm` within {BROADCAST_CONFIRM_WINDOW}s.")
                return
            pending_broadcast[chat_id] = {"text": reply.raw_text, "expires": time.time() + BROADCAST_CONFIRM_WINDOW}
            await event.edit(f"About to broadcast this text to ALL groups/channels you're in. Send `.bdc confirm` within {BROADCAST_CONFIRM_WINDOW}s to proceed, or ignore to cancel.")
            return
        pending = pending_broadcast.get(chat_id)
        if not pending or time.time() > pending["expires"]:
            await event.edit("No pending broadcast (or it expired). Reply to a message with `.bdc` again first.")
            return
        text = pending["text"]
        del pending_broadcast[chat_id]
        await event.edit("Broadcasting, this will take a while.")
        sent, skipped = 0, 0
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, User):
                continue
            try:
                await client.send_message(entity, text)
                sent += 1
                await asyncio.sleep(BROADCAST_DELAY_SECONDS)
            except ChatAdminRequiredError:
                skipped += 1
            except Exception:
                skipped += 1
        await client.send_message(chat_id, f"Broadcast done. Sent: {sent}, skipped: {skipped}.")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}leave$"))
async def cmd_leave(event):
    try:
        chat = await event.get_chat()
        if isinstance(chat, User):
            await event.edit(".leave only works in groups/channels.")
            return
        await event.edit("Leaving.")
        await client.delete_dialog(chat)
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}del$"))
async def cmd_del(event):
    try:
        reply = await get_reply_message(event)
        chat = await event.get_chat()
        if not reply:
            await event.edit("Usage: reply to a message with `.del`")
            return
        if isinstance(chat, User):
            await event.edit("Deleting full conversation for both sides.")
            all_ids = []
            async for msg in client.iter_messages(chat):
                all_ids.append(msg.id)
            for i in range(0, len(all_ids), 100):
                await client.delete_messages(chat, all_ids[i:i + 100], revoke=True)
        else:
            await client.delete_messages(chat, [reply.id], revoke=True)
            await event.respond("Message deleted for everyone.")
    except Exception as e:
        record_error(e)
        try:
            await event.edit(f"Error: {e}")
        except Exception:
            pass
@client.on(events.NewMessage(outgoing=True, pattern=rf"^\{COMMAND_PREFIX}fix$"))
async def cmd_fix(event):
    global last_error
    try:
        await event.edit("Attempting recovery.")
        if not client.is_connected():
            await client.connect()
        report = f"Last error: {last_error}" if last_error else "No recent errors logged."
        last_error = None
        await event.edit(f"Reconnected / reset. {report}")
    except Exception as e:
        record_error(e)
        await event.edit(f"Error: {e}")
async def main():
    await client.start()
    await client.run_until_disconnected()
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
