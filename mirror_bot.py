# tele_clone_targeted.py
# pip install telethon
import re
import time
import asyncio
from collections import defaultdict
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

API_ID = 24066461  # Replace with your actual API ID
API_HASH = "04d2e7ce7a20d9737960e6a69b736b4a"  # Replace with your actual API hash
SESSION = "clone.session"  # your user session file
TARGET_CHAT = "https://t.me/alphaniggasonly"  # final destination

# --- SOURCE CONFIG (numeric chat ID -> allowed sender usernames or numeric IDs) ---
# provided by you:
SOURCE_ALLOWLIST = {
    -1002418160348: ["hpmysize"],
    -1001896724165: ["micha211983", "saveyoda"],
    -1002584217226: ["ujmoulah", "oqure"],
    -1002677781471: [],
    -1001635741540: [],
    -1002514807546: ["nicolorenzo", "hey0xmax"],
}

# tuning
DUPLICATE_COOLDOWN_S = 60 * 60 * 4  # ignore same contract for 4 hours
MAX_MESSAGE_LENGTH = 1400

client = TelegramClient(SESSION, API_ID, API_HASH)

# regex patterns for common chains
RE_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
RE_TRON = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
RE_SOL = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

# dedupe store: contract -> last_seen_timestamp
recent = defaultdict(lambda: 0)

def normalize_sender_key(x):
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return str(x).lower()

# normalize SOURCE_ALLOWLIST to numeric/usernames lower
NORMALIZED_ALLOWLIST = {}
for chat, senders in SOURCE_ALLOWLIST.items():
    sset = set()
    for s in senders:
        sset.add(normalize_sender_key(s))
    NORMALIZED_ALLOWLIST[chat] = sset

def find_contracts(text):
    found = set()
    if not text:
        return found
    found.update(RE_ETH.findall(text))
    found.update(RE_TRON.findall(text))
    for m in RE_SOL.findall(text):
        if m.startswith("0x"): 
            continue
        if len(m) < 32: 
            continue
        if re.fullmatch(r"\d+", m):
            continue
        found.add(m)
    return found

@client.on(events.NewMessage(incoming=True))
async def handler(ev):
    try:
        msg = ev.message
        chat_id = msg.chat_id or (msg.to_id.chat_id if msg.to_id else None)
        print(f"DEBUG: Received new message in chat {chat_id}")
        if chat_id not in NORMALIZED_ALLOWLIST:
            print(f"DEBUG: Ignored - not in allowlist")
            return  # ignore all other groups

        sender = await msg.get_sender()
        print(f"DEBUG: Sender: {sender.username if sender else 'None'} (ID: {sender.id if sender else 'None'})")
        # determine sender id or username
        sender_id_key = normalize_sender_key(sender.id if sender else None)
        sender_username_key = (sender.username or "").lower() if sender and sender.username else None

        allowed = NORMALIZED_ALLOWLIST.get(chat_id, set())
        if allowed:
            if sender_id_key not in allowed and sender_username_key not in allowed:
                print(f"DEBUG: Ignored - sender not allowed")
                return  # only allowed senders per that chat if list is non-empty

        text = msg.message or ""
        contracts = find_contracts(text)
        if not contracts:
            print(f"DEBUG: Ignored - no contracts found in text: {text[:100]}...")
            return

        now = time.time()
        to_post = []
        for c in contracts:
            if now - recent[c] > DUPLICATE_COOLDOWN_S:
                to_post.append(c)
                recent[c] = now

        if not to_post:
            print(f"DEBUG: Ignored - duplicates within cooldown")
            return

        # Build safe plain-text post. Do NOT forward original message to avoid entities.
        sender_display = sender.username or (f"{sender.first_name or ''} {sender.last_name or ''}".strip()) or f"id{sender.id}"
        excerpt = (text[:MAX_MESSAGE_LENGTH] + ("..." if len(text) > MAX_MESSAGE_LENGTH else ""))
        post = f"{sender_display} in {chat_id} posted contract(s):\n\n" + "\n".join(to_post) + "\n\n" + excerpt

        print(f"DEBUG: Sending to target: {post[:100]}...")
        # Send as your account to target chat
        await client.send_message(TARGET_CHAT, post)
    except FloodWaitError as e:
        print(f"DEBUG: Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        # minimal logging
        print("Error:", repr(e))

async def cleanup_task():
    while True:
        now = time.time()
        stale = [k for k,v in recent.items() if now - v > DUPLICATE_COOLDOWN_S * 2]
        for k in stale:
            del recent[k]
        await asyncio.sleep(60 * 30)

async def main():
    await client.start()
    user = await client.get_me()
    print(f"DEBUG: Logged in as {user.username} (ID: {user.id})")
    print("Bot running under your account")
    # Optional: Check if joined to sources (will error if not)
    for chat_id in SOURCE_ALLOWLIST.keys():
        try:
            entity = await client.get_entity(chat_id)
            print(f"DEBUG: Joined to chat {chat_id} ({entity.title})")
        except Exception as e:
            print(f"DEBUG: Error accessing chat {chat_id}: {repr(e)}")
    client.loop.create_task(cleanup_task())
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
