from lib import MC_Server_Controller, ServerState, test_connection
import time
import discord
from discord.ext import commands
import asyncio
import yaml
import os
import json
from timeit import default_timer as timer

with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

BOT_TOKEN = config["bot_configs"]["bot_token"]
BOT_PREFIX = config["bot_configs"]["bot_prefix"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

MCSC = MC_Server_Controller()

@bot.event
async def on_ready():
    print('Logged on as {0}!'.format(bot.user))
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="you 👁️👄👁️"))
    if os.path.isfile("restart_info.json"):
        with open("restart_info.json", "r") as file:
            restart_info = json.load(file)
            if restart_info["dms"]:
                target_msg_id = restart_info["target_message_id"]
                target_msg_user_id = restart_info["user_id"]
                target_user = await bot.fetch_user(target_msg_user_id)
                target_channel = await target_user.create_dm()
                target_msg = await target_channel.fetch_message(target_msg_id)
                time_taken = timer() - restart_info["restart_time"]
                await target_msg.edit(content=f"```\nVM restarted in {int(time_taken)}s\n```")
            else:                
                target_msg_id = restart_info["target_message_id"]
                target_msg_channel = restart_info["target_message_channel"]
                target_channel = bot.get_channel(target_msg_channel)
                target_msg = await target_channel.fetch_message(target_msg_id)
                time_taken = timer() - restart_info["restart_time"]
                await target_msg.edit(content=f"```\nVM restarted in {int(time_taken)}s\n```")
        os.remove("restart_info.json")


@bot.command()
async def ping(ctx):
    print('Ping recieved from {0}'.format(ctx.author))
    
    start_time = time.perf_counter()
    message = await ctx.send("Calculating ping...")
    end_time = time.perf_counter()
    processing_latency = int((end_time - start_time) * 1000)
    
    connection_latency = test_connection()
    ping_message = f"```\n\
        ╔                           ╗\n\
█═╦═════╣           Ping            ║\n\
  ║     ╚                           ╝\n\
  ╠══│ Host Ping: {connection_latency}ms\n\
  ╚══│ Processing Time: {processing_latency}ms\n```"
    await message.edit(content=ping_message)
    print(f'Ponged')


@bot.command()
async def mc(ctx, *args):
    if len(args) < 1:
        await ctx.channel.send("```\nNo args given\n```")
    else:
        match args[0].lower():
            case "start":
                await mcStart(ctx.channel)
            case "stop":
                await mcStop(ctx.channel)
            case "get_log":
                await mcGetLog(ctx.channel, args[1])
            case "status":
                await mcStatus(ctx.channel)
            case "list_logs":
                if len(args) == 1:
                    await mcListLogs(ctx.channel, None)
                else:
                    await mcListLogs(ctx.channel, args[1])
            case "recent_logs":
                await mcLiveLogBuffer(ctx.channel)
            case "status":
                await mcStatus(ctx.channel)
            case _:
                print(f"Invalid Minecraft arguments: {args}")
        # elif (args[0].lower() == "info"):
        #     await mcInfo(ctx.channel)
        # elif (args[0].lower() == "op"):
        #     await mcOP(ctx.channel, args[1])
    
async def mcStart(channel):
    match MCSC.server_state:
        case ServerState.OFF:
            boot_message = await channel.send("```\nRequesting the server controller to boot up the server...\n```")
            await bot.change_presence(activity=discord.Game(name="Booting Minecraft Server..."))
            await MCSC.start(boot_message)
            await bot.change_presence(activity=discord.Game(name="Minecraft Server Management"))        
        case ServerState.ON:
            await channel.send(f"```\nServer is already online at: {MCSC.server_access_point}\n```")
        case ServerState.STARTING:
            synnced_message = await channel.send("```\nSever is already starting up, syncing progress...\n```")
            await MCSC.synced_starting_msg(synnced_message)
        case ServerState.STOPPING:
            await channel.send(f"```\nServer is already shutting down, wait for it to completely shut off before starting again.\n```")
    
async def mcStop(channel):
    match MCSC.server_state:
        case ServerState.ON:
            stop_message = await channel.send("```\nRequesting the server controller to stop the server...\n```")
            await MCSC.stop(stop_message)
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="you 👁️👄👁️"))
        case ServerState.STARTING:
            await channel.send("```\nWait until the server is on to turn it shut it down.\n```")
        case ServerState.OFF:
            await channel.send("```\nThe server is already off.\n```")
        case ServerState.STOPPING:
            await channel.send("```\nThe server is already shutting down.\n```")

async def mcStatus(channel):
    status_message = f"```\n\
        ╔                           ╗\n\
█═╦═════╣       Server Status       ║\n\
  ║     ╚                           ╝\n"
    
    match MCSC.server_state:
        case ServerState.ON:
            status_info = await MCSC.connected_players()
            if status_info[0] == 0:
                status_message += f"  ╠══│ Server is online.\n"
                status_message += f"  ╚══│ Number of players online: {status_info[0]}\n```"
            else:
                status_message += f"  ╠══│ Server is online.\n"
                status_message += f"  ╠══│ Number of players online: {status_info[0]}\n"
                status_message += f"  ╚══│ Player Online: {status_info[1]}\n```"
        case ServerState.OFF:
            status_message += f"  ╚══│ The server is currently off.\n```"
        case ServerState.STARTING:
            status_message += f"  ╚══│ The server is starting up, is [!mc start] to see the progress.\n```"
        case ServerState.STOPPING:
            status_message += f"  ╚══│ The server is shutting down.\n```"
            
    await channel.send(status_message)

async def mcGetLog(channel, file_name):
    log_message = await channel.send("```\nRequesting logs from the server controller...\n```")
    await MCSC.get_log(channel, log_message, file_name)

async def mcListLogs(channel, last_x=None):
    list_message = await channel.send("```\nRequesting file names from the server controller...\n```")
    await MCSC.list_logs(list_message, last_x)

async def mcLiveLogBuffer(channel):
    buffer_msg = await channel.send("```\nRequesting logs from the server controller...\n```")
    await MCSC.get_live_log_buffer(buffer_msg)

@bot.command()
async def restart_vm(ctx):
    restart_message = await ctx.channel.send("```\nRestarting Virtual Machine...\n```")
    with open("restart_info.json", "w") as file:
        if ctx.guild is None:
            info = {
                "dms": True,
                "restart_time": timer(),
                "target_message_id": restart_message.id,
                "user_id": ctx.author.id
            }
        else:
            info = {
                "dms": False,
                "restart_time": timer(),
                "target_message_id": restart_message.id,
                "target_message_channel": restart_message.channel.id
            }
        json.dump(info, file)
    os.system("shutdown /r /t 3 /c \"MOB is restarting this VM\"")

bot.run(BOT_TOKEN)