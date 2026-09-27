import asyncio
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

import discord


# ============================================================
# EINSTELLUNGEN
# ============================================================

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

YOUTUBE_HANDLES = {
    "ULBIDE": "https://www.youtube.com/@ulbiede",
    "MYKA_JO": "https://www.youtube.com/@Myka_jo",
}

STATE_FILE = "posted_videos.json"

ATOM = "{http://www.w3.org/2005/Atom}"
YOUTUBE = "{http://www.youtube.com/xml/schemas/2015}"


# ============================================================
# YOUTUBE-KANAL-ID AUS DEM @HANDLE ERMITTELN
# ============================================================

def get_channel_id(handle_url):
    request = urllib.request.Request(
        handle_url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")

    # Sucht nach einer normalen YouTube-Kanal-ID, z. B.
    # UCxxxxxxxxxxxxxxxxxxxxxx
    match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]+)"', html)

    if not match:
        match = re.search(
            r'"externalId":"(UC[a-zA-Z0-9_-]+)"',
            html
        )

    if not match:
        raise RuntimeError(
            f"Kanal-ID konnte nicht gefunden werden: {handle_url}"
        )

    return match.group(1)


# ============================================================
# NEUE VIDEOS AUS DEM YOUTUBE-RSS-FEED HOLEN
# ============================================================

def get_videos(channel_id):
    feed_url = (
        "https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )

    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    videos = []

    for entry in root.findall(f"{ATOM}entry"):
        video_id = entry.findtext(f"{YOUTUBE}videoId")
        title = entry.findtext(f"{ATOM}title")
        published = entry.findtext(f"{ATOM}published")

        video_url = None

        for link in entry.findall(f"{ATOM}link"):
            if link.get("rel") == "alternate":
                video_url = link.get("href")
                break

        if video_id and video_url:
            videos.append(
                {
                    "id": video_id,
                    "title": title or "Neues Video",
                    "url": video_url,
                    "published": published or "",
                }
            )

    # Ältestes neues Video zuerst
    videos.sort(key=lambda video: video["published"])

    return videos


# ============================================================
# BEREITS GEPOSTETE VIDEOS LADEN
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except (json.JSONDecodeError, OSError):
        return set()


# ============================================================
# BEREITS GEPOSTETE VIDEOS SPEICHERN
# ============================================================

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sorted(state),
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# DISCORD
# ============================================================

async def send_new_videos(new_videos):
    intents = discord.Intents.none()
    client = discord.Client(intents=intents)

    try:
        await client.login(DISCORD_TOKEN)

        channel = client.get_channel(DISCORD_CHANNEL_ID)

        if channel is None:
            channel = await client.fetch_channel(DISCORD_CHANNEL_ID)

        for channel_name, video in new_videos:
            message = (
                f"**{channel_name} – neues Video!**\n"
                f"{video['title']}\n"
                f"{video['url']}"
            )

            await channel.send(message)

            print(
                f"Gesendet: {channel_name} - {video['title']}"
            )

    finally:
        await client.close()


# ============================================================
# HAUPTPROGRAMM
# ============================================================

async def main():
    state = load_state()

    # Beim allerersten Start werden vorhandene Videos nur
    # als "bereits gesehen" gespeichert.
    # Dadurch spammt der Bot nicht direkt alle alten Videos
    # in euren Discord-Kanal.
    first_run = state is None

    if first_run:
        state = set()

    new_videos = []

    for channel_name, handle_url in YOUTUBE_HANDLES.items():
        print(f"Prüfe {channel_name}...")

        channel_id = get_channel_id(handle_url)

        print(f"Kanal-ID gefunden: {channel_id}")

        videos = get_videos(channel_id)

        if first_run:
            for video in videos:
                state.add(video["id"])

        else:
            for video in videos:
                if video["id"] not in state:
                    new_videos.append(
                        (channel_name, video)
                    )

    if first_run:
        save_state(state)
        print(
            "Erster Start abgeschlossen. "
            "Vorhandene Videos wurden als gesehen gespeichert."
        )
        return

    if not new_videos:
        print("Keine neuen Videos gefunden.")
        return

    # Neue Videos an Discord senden
    await send_new_videos(new_videos)

    # Erst nach erfolgreichem Senden speichern
    for channel_name, video in new_videos:
        state.add(video["id"])

    save_state(state)

    print(
        f"{len(new_videos)} neues/neue Video(s) verarbeitet."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
