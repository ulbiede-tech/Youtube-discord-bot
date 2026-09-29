import asyncio
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import discord


# =========================
# Discord Einstellungen
# =========================

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

# Kanal für die Server-Mitgliederzahl
STATS_CHANNEL_ID = 1481035272626901304


# =========================
# YouTube Kanäle
# =========================

YOUTUBE_HANDLES = {
    "ULBIDE": "https://www.youtube.com/@ulbiede",
    "MYKA_JO": "https://www.youtube.com/@Myka_jo",
}


# Angezeigte Namen in Discord
DISPLAY_NAMES = {
    "ULBIDE": "ULBIEDE",
    "MYKA_JO": "MYKA_JO",
}


# =========================
# Einstellungen
# =========================

STATE_FILE = "posted_videos.json"

# Beim allerersten Start das aktuellste Video senden
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

        # Schutz gegen falsches Format
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
# Server-Mitgliederzahl aktualisieren
# =========================

async def update_server_stats(client):
    try:
        stats_channel = client.get_channel(
            STATS_CHANNEL_ID
        )

        if stats_channel is None:
            stats_channel = await client.fetch_channel(
                STATS_CHANNEL_ID
            )

        if not isinstance(
            stats_channel,
            discord.abc.GuildChannel
        ):
            raise RuntimeError(
                "Die angegebene ID ist kein Server-Kanal."
            )

        guild = stats_channel.guild

        print(
            f"Server gefunden: {guild.name}"
        )

        print(
            f"Server-ID: {guild.id}"
        )

        # Mitglieder direkt über die Discord-API abrufen
        members = [
            member
            async for member in guild.fetch_members(
                limit=None
            )
        ]

        member_count = len(members)

        print(
            f"Aktuelle Mitgliederzahl: {member_count}"
        )

        print(
            f"Aktueller Stats-Kanalname: "
            f"{stats_channel.name}"
        )

        new_name = f"Members {member_count}"

        if stats_channel.name != new_name:

            await stats_channel.edit(
                name=new_name,
                reason=(
                    "Ulmy Interactive: "
                    "Mitgliederzahl aktualisieren"
                )
            )

            print(
                f"Stats-Kanal erfolgreich geändert zu: "
                f"{new_name}"
            )

        else:

            print(
                "Stats-Kanal ist bereits aktuell."
            )

    except discord.Forbidden:
        print(
            "FEHLER: Ulmy Interactive darf den "
            "Stats-Kanal nicht bearbeiten. "
            "Prüfe 'Kanäle verwalten' für diesen Kanal."
        )

    except Exception as error:
        print(
            f"Fehler beim Aktualisieren "
            f"des Stats-Kanals: {error}"
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

        # Der obere Text ist NICHT klickbar.
        # Nur der eigentliche Videotitel ist klickbar.
        embed = discord.Embed(
            description=(
                f"**{display_name} published a new video!**"
                f"\n\n"
                f"[{video['title']}]({video['url']})"
            ),
            color=0x33FF00
        )

        # YouTube-Vorschaubild
        embed.set_image(
            url=thumbnail_url
        )

        # @everyone erlauben
        allowed_mentions = discord.AllowedMentions(
            everyone=True
        )

        # Kein zusätzlicher YouTube-Link als Text
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

    print(
        "Bot-Start:",
        datetime.now(timezone.utc).isoformat()
    )

    # Members Intent aktivieren
    intents = discord.Intents.default()
    intents.members = True

    client = discord.Client(
        intents=intents
    )

    state = load_state()

    async with client:

        await client.login(DISCORD_TOKEN)

        # =========================
        # Server Stats aktualisieren
        # =========================

        await update_server_stats(client)

        # =========================
        # YouTube Discord Kanal
        # =========================

        channel = client.get_channel(
            DISCORD_CHANNEL_ID
        )

        if channel is None:
            channel = await client.fetch_channel(
                DISCORD_CHANNEL_ID
            )

        # =========================
        # YouTube prüfen
        # =========================

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

                # Anzeigen, welches Video YouTube
                # momentan als neuestes liefert
                print(
                    f"Neuestes Feed-Video für "
                    f"{channel_name}: "
                    f"{videos[0]['title']} "
                    f"({videos[0]['id']})"
                )

                seen_videos = state.get(
                    channel_name,
                    []
                )

                # =========================
                # Erster Start
                # =========================

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

                # =========================
                # Normale Prüfung
                # =========================

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

                    else:
                        print(
                            f"Keine neuen Videos "
                            f"von {channel_name}"
                        )

            except Exception as error:

                print(
                    f"Fehler bei "
                    f"{channel_name}: "
                    f"{error}"
                )

        # =========================
        # Zustand speichern
        # =========================

        save_state(state)

        await client.close()

        print("Bot fertig.")


# =========================
# Start
# =========================

if __name__ == "__main__":
    asyncio.run(main())
