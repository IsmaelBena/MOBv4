from lib import MC_Server_Controller, ServerState, test_connection
import time
import discord
from discord.ext import commands
import asyncio
import yaml
import os

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
        if (args[0].lower() == "start"):
            await mcStart(ctx.channel)
        elif (args[0].lower() == "stop"):
            await mcStop(ctx.channel)
        elif (args[0].lower() == "get_log"):
            await mcGetLog(ctx.channel, args[1])
        elif (args[0].lower() == "status"):
            await mcStatus(ctx.channel)
        elif (args[0].lower() == "list_logs"):
            if len(args) == 1:
                await mcListLogs(ctx.channel, None)
            else:
                await mcListLogs(ctx.channel, args[1])
        else:
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
            await channel.send("```\nServer is already online at: 0.0.0.0\n```")
        case ServerState.STARTING:
            synnced_message = await channel.send("```\nSever is already starting up, syncing progress...\n```")
            await MCSC.synced_starting_msg(synnced_message)
        case ServerState.STOPPING:
            await channel.send(f"```\nServer is already shutting down, wait for it completely shut off before starting again.\n```")
    
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
                status_message += f"  ╚══│ Number of players online: {status_info[1]}\n```"
        case ServerState.OFF:
            status_message += f"  ╚══│ The server is currently off.\n```"
        case ServerState.STARTING:
            status_message += f"  ╚══│ The server is already starting up, is [!mc start] to see the progress.\n```"
        case ServerState.STOPPING:
            status_message += f"  ╚══│ The server is shutting down.\n```"
            
    await channel.send(status_message)

async def mcGetLog(channel, file_name):
    log_message = await channel.send("```\nRequesting logs from the server controller...\n```")
    await MCSC.get_log(channel, log_message, file_name)

async def mcListLogs(channel, last_x=None):
    list_message = await channel.send("```\nRequesting file names from the server controller...\n```")
    await MCSC.list_logs(list_message, last_x)


@bot.command()
async def restart_vm(ctx):
    await ctx.channel.send("```\nRestarting Virtual Machine...\n```")
    os.system("shutdown /r /t 3 /c \"MOB is restarting this VM\"")

bot.run(BOT_TOKEN)