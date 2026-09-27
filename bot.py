import asyncio
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

import discord


# =========================
# Discord Einstellungen
# =========================

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])


# =========================
# YouTube Kanäle
# =========================

YOUTUBE_HANDLES = {
    "ULBIEDE": "https://www.youtube.com/@ulbiede",
    "MYKA_JO": "https://www.youtube.com/@Myka_jo",
}


# Angezeigte Namen in Discord
DISPLAY_NAMES = {
    "ULBIEDE": "ULBIEDE",
    "MYKA_JO": "MYKA_JO",
}


# =========================
# Einstellungen
# =========================

STATE_FILE = "posted_videos.json"

SEND_LATEST_ON_FIRST_RUN = True


# =========================
# YouTube Channel-ID finden
# =========================

def get_channel_id(handle_url):
    request = urllib.request.Request(
        handle_url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode(
            "utf-8",
            errors="ignore"
        )

    match = re.search(
        r'"channelId":"(UC[^"]+)"',
        html
    )

    if not match:
        match = re.search(
            r'"externalId":"(UC[^"]+)"',
            html
        )

    if not match:
        raise RuntimeError(
            f"Keine YouTube Channel-ID gefunden: {handle_url}"
        )

    return match.group(1)


# =========================
# Videos eines Kanals holen
# =========================

def get_videos(channel_id):
    url = (
        "https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    namespace = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }

    videos = []

    for entry in root.findall(
        "atom:entry",
        namespace
    ):
        video_id = entry.findtext(
            "yt:videoId",
            default="",
            namespaces=namespace
        )

        title = entry.findtext(
            "atom:title",
            default="",
            namespaces=namespace
        )

        if not video_id:
            continue

        videos.append({
            "id": video_id,
            "title": title,
            "url": (
                f"https://www.youtube.com/watch?v={video_id}"
            ),
        })

    return videos


# =========================
# Gespeicherte Videos laden
# =========================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        # Falls die Datei aus irgendeinem Grund
        # kein Dictionary ist, starten wir sauber neu.
        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


# =========================
# Gespeicherte Videos speichern
# =========================

def save_state(state):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False
        )


# =========================
# Video an Discord senden
# =========================

async def send_new_videos(
    channel,
    channel_name,
    videos
):
    display_name = DISPLAY_NAMES.get(
        channel_name,
        channel_name
    )

    for video in reversed(videos):

        # YouTube-Vorschaubild
        thumbnail_url = (
            f"https://img.youtube.com/vi/"
            f"{video['id']}/hqdefault.jpg"
        )

        # Grüner Discord-Embed
        embed = discord.Embed(
            title=(
                f"{display_name} "
                f"published a new video!"
            ),
            description=video["title"],
            url=video["url"],
            color=0x33FF00
        )

        # YouTube-Thumbnail als Vorschau
        embed.set_image(
            url=thumbnail_url
        )

        # @everyone erlauben
        allowed_mentions = discord.AllowedMentions(
            everyone=True
        )

        # KEIN YouTube-Link als extra Text!
        await channel.send(
            content="@everyone",
            embed=embed,
            allowed_mentions=allowed_mentions
        )

        await asyncio.sleep(2)


# =========================
# Hauptprogramm
# =========================

async def main():

    intents = discord.Intents.default()

    client = discord.Client(
        intents=intents
    )

    state = load_state()

    async with client:

        await client.login(DISCORD_TOKEN)

        channel = client.get_channel(
            DISCORD_CHANNEL_ID
        )

        if channel is None:
            channel = await client.fetch_channel(
                DISCORD_CHANNEL_ID
            )

        for channel_name, handle_url in YOUTUBE_HANDLES.items():

            try:
                print(
                    f"Prüfe YouTube-Kanal "
                    f"{channel_name}"
                )

                channel_id = get_channel_id(
                    handle_url
                )

                videos = get_videos(
                    channel_id
                )

                if not videos:
                    print(
                        f"Keine Videos gefunden: "
                        f"{channel_name}"
                    )
                    continue

                seen_videos = state.get(
                    channel_name,
                    []
                )

                # Erster Start
                if channel_name not in state:

                    if SEND_LATEST_ON_FIRST_RUN:
                        await send_new_videos(
                            channel,
                            channel_name,
                            videos[:1]
                        )

                    state[channel_name] = [
                        video["id"]
                        for video in videos
                    ]

                else:

                    new_videos = [
                        video
                        for video in videos
                        if video["id"]
                        not in seen_videos
                    ]

                    if new_videos:

                        print(
                            f"{len(new_videos)} "
                            f"neue(s) Video(s) "
                            f"von {channel_name}"
                        )

                        await send_new_videos(
                            channel,
                            channel_name,
                            new_videos
                        )

                        state[channel_name] = (
                            seen_videos
                            + [
                                video["id"]
                                for video in new_videos
                            ]
                        )

            except Exception as error:

                print(
                    f"Fehler bei "
                    f"{channel_name}: "
                    f"{error}"
                )

        save_state(state)

        await client.close()


# =========================
# Start
# =========================

if __name__ == "__main__":
    asyncio.run(main())
