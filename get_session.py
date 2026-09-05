from telethon import TelegramClient
from telethon.sessions import StringSession
api_id = int(input("API ID: "))
api_hash = input("API Hash: ")
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())
