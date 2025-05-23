import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import Embed, ButtonStyle
import json
import os
import aiohttp
import asyncio

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

DATA_FILE = "data.json"
YOUTUBE_API_KEY = "youtube_api_key"
TWITCH_CLIENT_ID = "twitch_client_id"
TWITCH_CLIENT_SECRET = "twitch_client_secret"
twitch_token = None  # Globales Token, wird später gefüllt

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"youtube": {}, "twitch": {}}, f)


def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def get_twitch_token():
    global twitch_token
    if twitch_token is None:
        async with aiohttp.ClientSession() as session:
            token_url = "https://id.twitch.tv/oauth2/token"
            params = {
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            }
            async with session.post(token_url, params=params) as r:
                twitch_token = (await r.json())["access_token"]
    return twitch_token


# ======= YOUTUBE =========

@bot.tree.command(name="ab_yt_dcc_add")
async def ab_yt_dcc_add(interaction: discord.Interaction, dc_channel: discord.TextChannel, yt_tag: str):
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    res = yt.channels().list(part="contentDetails", id=yt_tag).execute()
    uploads_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids = yt.playlistItems().list(playlistId=uploads_id, part="snippet", maxResults=1).execute()
    if vids["items"]:
        latest = vids["items"][0]["snippet"]
        embed = await create_youtube_embed(latest)
        await dc_channel.send(embed=embed)

    data = load_data()
    if yt_tag not in data["youtube"]:
        data["youtube"][yt_tag] = {"channels": [], "text": "Neues Video: {title} - {url}", "last_video": None}
    if dc_channel.id not in data["youtube"][yt_tag]["channels"]:
        data["youtube"][yt_tag]["channels"].append(dc_channel.id)
    save_data(data)
    await interaction.response.send_message(f"✅ `{yt_tag}` wird jetzt im Channel {dc_channel.mention} verfolgt.", ephemeral=True)


@bot.tree.command(name="ab_yt_dcc_remove")
async def ab_yt_dcc_remove(interaction: discord.Interaction, dc_channel: discord.TextChannel, yt_tag: str):
    data = load_data()
    if yt_tag in data["youtube"] and dc_channel.id in data["youtube"][yt_tag]["channels"]:
        data["youtube"][yt_tag]["channels"].remove(dc_channel.id)
        save_data(data)
        await interaction.response.send_message(f"❌ `{yt_tag}` wird im Channel {dc_channel.mention} nicht mehr verfolgt.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Dieser Kanal wurde nicht gefunden.", ephemeral=True)


@bot.tree.command(name="ab_yt_dcc_text")
async def ab_yt_dcc_text(interaction: discord.Interaction, yt_tag: str, text: str):
    data = load_data()
    if yt_tag in data["youtube"]:
        data["youtube"][yt_tag]["text"] = text
        save_data(data)
        await interaction.response.send_message("✅ Text aktualisiert.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ YouTube-Tag wurde nicht gefunden.", ephemeral=True)

# ======= TWITCH =========

@bot.tree.command(name="ab_ttv_dcc_add")
async def ab_ttv_dcc_add(interaction: discord.Interaction, dc_channel: discord.TextChannel, twitch_tag: str):
    async with aiohttp.ClientSession() as session:
        token = await get_twitch_token()
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        async with session.get(f"https://api.twitch.tv/helix/users?login={twitch_tag}", headers=headers) as user_req:
            user_data = (await user_req.json())["data"][0]
            profile_img = user_data["profile_image_url"]
            display_name = user_data["display_name"]
            embed = await create_twitch_embed(twitch_tag, profile_img, f"Vorschau: {display_name} ist live!")
            await dc_channel.send(embed=embed)

    data = load_data()
    if twitch_tag not in data["twitch"]:
        data["twitch"][twitch_tag] = {"channels": [], "text": "{name} ist jetzt live: {url}", "is_live": False}
    if dc_channel.id not in data["twitch"][twitch_tag]["channels"]:
        data["twitch"][twitch_tag]["channels"].append(dc_channel.id)
    save_data(data)
    await interaction.response.send_message(f"✅ `{twitch_tag}` wird jetzt im Channel {dc_channel.mention} verfolgt.", ephemeral=True)


@bot.tree.command(name="ab_ttv_dcc_remove")
async def ab_ttv_dcc_remove(interaction: discord.Interaction, dc_channel: discord.TextChannel, twitch_tag: str):
    data = load_data()
    if twitch_tag in data["twitch"] and dc_channel.id in data["twitch"][twitch_tag]["channels"]:
        data["twitch"][twitch_tag]["channels"].remove(dc_channel.id)
        save_data(data)
        await interaction.response.send_message(f"❌ `{twitch_tag}` wird im Channel {dc_channel.mention} nicht mehr verfolgt.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Dieser Kanal wurde nicht gefunden.", ephemeral=True)


@bot.tree.command(name="ab_ttv_dcc_text")
async def ab_ttv_dcc_text(interaction: discord.Interaction, twitch_tag: str, text: str):
    data = load_data()
    if twitch_tag in data["twitch"]:
        data["twitch"][twitch_tag]["text"] = text
        save_data(data)
        await interaction.response.send_message("✅ Text aktualisiert.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Twitch-Tag wurde nicht gefunden.", ephemeral=True)


# ===== RESET =====

@bot.tree.command(name="ab_reset")
async def ab_reset(interaction: discord.Interaction):
    with open(DATA_FILE, "w") as f:
        json.dump({"youtube": {}, "twitch": {}}, f)
    await interaction.response.send_message("🗑️ Daten wurden zurückgesetzt.", ephemeral=True)


# ======= TASKS ==========discord.ext

async def create_youtube_button(yt_data):
    video_url = "https://youtu.be/" + yt_data["resourceId"]["videoId"]
    view = View()
    view.add_item(Button(label="Zum Video", url=video_url, style=ButtonStyle.link))
    return view

async def create_youtube_embed(yt_data):
    video_id = yt_data["resourceId"]["videoId"]
    title = yt_data["title"]
    channel_title = yt_data["channelTitle"]
    thumbnail = yt_data["thumbnails"]["high"]["url"]
    channel_url = f"https://www.youtube.com/channel/{yt_data['channelId']}"

    embed = discord.Embed(
        title=f"{channel_title} hat ein neues Video hochgeladen.",
        url=f"https://youtu.be/{video_id}",
        description=title,
        color=0xFF0000
    )
    embed.set_thumbnail(url=thumbnail)
    embed.set_footer(text="YouTube Upload")
    embed.timestamp = discord.utils.utcnow()
    return embed


async def create_twitch_button(twitch_name):
    view = View()
    view.add_item(Button(label="Zum Stream", url=f"https://twitch.tv/{twitch_name}", style=ButtonStyle.link))
    return view

async def create_twitch_embed(twitch_name, profile_img_url, stream_title):
    embed = discord.Embed(
        title=stream_title,
        url=f"https://twitch.tv/{twitch_name}",
        description=f"🔴 {twitch_name} ist jetzt live!",
        color=0x9146FF
    )
    embed.set_thumbnail(url=profile_img_url)
    embed.set_footer(text="Twitch Livestream")
    embed.timestamp = discord.utils.utcnow()
    return embed



@tasks.loop(minutes=1)
async def check_youtube():
    from googleapiclient.discovery import build
    data = load_data()
    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    for tag, info in data["youtube"].items():
        try:
            # Verwende YouTube-Kanal-ID direkt (nicht Username!)
            req = yt.channels().list(part="contentDetails", id=tag)
            res = req.execute()
            if "items" not in res or not res["items"]:
                #print(f"❌ Kein Kanal mit ID {tag} gefunden.")
                continue

            uploads_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            vids = yt.playlistItems().list(playlistId=uploads_id, part="snippet", maxResults=1).execute()

            if not vids["items"]:
                continue

            latest = vids["items"][0]["snippet"]
            video_id = latest["resourceId"]["videoId"]

            # Wenn erstes Mal → speichere nur, sende nichts
            if info.get("last_video") is None:
                embed = await create_youtube_embed(latest)
                for channel_id in info["channels"]:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=embed)

                data["youtube"][tag]["last_video"] = video_id
                #print(f"🔍 Erstes Video gespeichert für {tag}: {video_id}")
                continue

            # Wenn neues Video
            if video_id != info["last_video"]:
                data["youtube"][tag]["last_video"] = video_id
                for channel_id in info["channels"]:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        embed = await create_youtube_embed(latest)
                        await channel.send(embed=embed)
                #print(f"📢 Neues Video bei {tag}: {video_id}")
            else:
                #print(f"⏳ Kein neues Video für {tag}.")
                pass
        except Exception as e:
            #print(f"[YouTube] Fehler bei {tag}: {e}")
            continue

    save_data(data)


@tasks.loop(minutes=1)
async def check_twitch():
    data = load_data()
    async with aiohttp.ClientSession() as session:
        # Auth Token holen
        token_url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        async with session.post(token_url, params=params) as r:
            twitch_token = (await r.json())["access_token"]
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {twitch_token}",
        }

        for tag, info in data["twitch"].items():
            async with session.get(f"https://api.twitch.tv/helix/streams?user_login={tag}", headers=headers) as r:
                resp = await r.json()
                is_now_live = len(resp["data"]) > 0
                if is_now_live and not info.get("is_live", False):
                    info["is_live"] = True
                    stream_info = resp["data"][0]
                    stream_title = stream_info["title"]

                    # Profilbild abrufen
                    async with session.get(f"https://api.twitch.tv/helix/users?login={tag}", headers=headers) as user_req:
                        user_data = (await user_req.json())["data"][0]
                        profile_img = user_data["profile_image_url"]

                    embed = await create_twitch_embed(tag, profile_img, stream_title)
                    for channel_id in info["channels"]:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            await channel.send(embed=embed)

                elif not is_now_live:
                    info["is_live"] = False
    save_data(data)


@bot.event
async def on_ready():
    await bot.tree.sync()
    check_youtube.start()
    check_twitch.start()

    # YouTube-Embeds bei Start
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    data = load_data()

    for tag, info in data.get("youtube", {}).items():
        try:
            res = yt.channels().list(part="contentDetails", id=tag).execute()
            uploads_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            vids = yt.playlistItems().list(playlistId=uploads_id, part="snippet", maxResults=1).execute()
            if vids["items"]:
                latest = vids["items"][0]["snippet"]
                embed = await create_youtube_embed(latest)
                view = await create_youtube_button(latest)
                for ch_id in info["channels"]:
                    ch = bot.get_channel(ch_id)
                    #print(f"[YT-DEBUG] Channel-ID {ch_id}: {ch}")
                    if ch:
                        await ch.send(embed=embed, view=view)
        except Exception as e:
            #print(f"[Start-Fehler YT {tag}]: {e}")
            pass

    # Twitch-Embeds bei Start
    async with aiohttp.ClientSession() as session:
        token = await get_twitch_token()
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }

        for tag, info in data.get("twitch", {}).items():
            try:
                async with session.get(f"https://api.twitch.tv/helix/users?login={tag}", headers=headers) as user_req:
                    user_data = (await user_req.json())["data"][0]
                    profile_img = user_data["profile_image_url"]
                    display_name = user_data["display_name"]
                    embed = await create_twitch_embed(tag, profile_img, f"{display_name} ist live (Teststart)")
                    view = await create_twitch_button(tag)

                    for ch_id in info["channels"]:
                        ch = bot.get_channel(ch_id)
                        if ch:
                            await ch.send(embed=embed, view=view)
            except Exception as e:
                #print(f"[Start-Fehler TW {tag}]: {e}")
                pass



# ======= START BOT =======

bot.run("discord_bot_token")
