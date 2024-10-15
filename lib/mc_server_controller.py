import subprocess
import os
from enum import Enum
import yaml
import json
from jproperties import Properties
import threading
import logging
from datetime import datetime
import time
from timeit import default_timer as timer
import asyncio
import discord
import urllib.request
from collections import deque
import itertools

#################################################################################
#                                                                               #
#                           Server State Enum Class                             #
#                                                                               #
#################################################################################

class ServerState(Enum):
    ON = 1
    OFF = 2
    STARTING = 3
    STOPPING = 4


#################################################################################
#                                                                               #
#                    Minecraft Server Controller Class                          #
#                                                                               #
#################################################################################

class MC_Server_Controller:
    def __init__(self, bot):
        print("Initialising Minecraft Server Controller")
        with open('config.yaml', 'r') as file:
            config = yaml.safe_load(file)
        
        self.server_dir = config["minecraft_configs"]["server_directory"]
        self.start_script = config["minecraft_configs"]["start_script"]
        self.server_mob_info_path = os.path.join(self.server_dir, "mob_server_info.json")
        
        self.default_channel = config["bot_configs"]["default_channel"]
        self.bot = bot
        
        if os.path.isfile(self.server_mob_info_path):
            with open(self.server_mob_info_path, 'r') as file:
                self.server_mob_info = json.load(file)
        else:
            with open(self.server_mob_info_path, 'w') as file:
                blank_info = {
                    'modpack_name': '',
                    'boot_times': []
                }
                json.dump(blank_info, file)
        
            self.server_mob_info = blank_info
        
        if len(self.server_mob_info["boot_times"]) == 0:
            self.average_boot_time = 0
        else:
            self.average_boot_time = sum(self.server_mob_info["boot_times"]) / float(len(self.server_mob_info["boot_times"]))
        
        self.read_server_properties()
        
        if config["minecraft_configs"]["auto_detect_ip"]:
            self.server_access_point = f"{urllib.request.urlopen('https://v4.ident.me').read().decode('utf8')}:{self.server_port}"
        else:
            self.server_access_point =config["minecraft_configs"]["custom_access_point"]
        
        self.server_process = None
        self.log_dir = os.path.join(os.getcwd(), config["minecraft_configs"]["logs_directory"])
        
        self.online_indicator = config["minecraft_configs"]["online_indicator"]
        self.shutdown_indicator = config["minecraft_configs"]["shutdown_indicator"]
        
        self.server_state = ServerState.OFF
        self.booting_progress = None
        self.booting_progress_msg = None
        self.last_log_file = None

        
    #####################################################################################
    #                  Read Properties from server.properties file                      #
    #####################################################################################
        
    def read_server_properties(self):
        server_properties = Properties()
        with open(os.path.join(self.server_dir, 'server.properties'), 'rb') as server_properties_file:
            server_properties.load(server_properties_file)
        
        # User displayed details
        self.server_port = server_properties.get("query.port").data
        self.difficulty = server_properties.get("difficulty").data
        self.hardcore = server_properties.get("hardcore").data
        self.gamemode = server_properties.get("gamemode").data

    #####################################################################################
    #                               Start the server                                    #
    #####################################################################################

    async def start(self, boot_message):     
        # Check if the server is on
        if self.server_process is not None:
            # respond with there is an active server process
            print(" │ MCSC.start │ Server is already running")
            return
        try:
            self.server_state = ServerState.STARTING
            self.last_30_log = deque([], maxlen=30)
            start_time = timer()
            current_datetime = datetime.now()
            formatted_timestamp = current_datetime.strftime("%d-%m-%Y_%H-%M-%S")
            if not os.path.exists(os.path.join(os.getcwd(), self.log_dir)):
                os.makedirs(os.path.join(os.getcwd(), self.log_dir))
            log_file = os.path.join(os.getcwd(), self.log_dir, f"{formatted_timestamp}.log")
            self.last_log_file = log_file
            open(log_file, "x")
            print(f" │ MCSC.start │ Log file created at: {log_file}")
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(message)s',
                handlers=[
                    logging.FileHandler(os.path.join(self.log_dir, f"{formatted_timestamp}.log"))
                    # logging.StreamHandler()  # Outputs to console as well
                ]
            )
            print(f" │ MCSC.start │ Created logger with timestap: {formatted_timestamp}")
            # Creating server process
            self.server_process = subprocess.Popen(
                f"{os.path.join(self.server_dir, self.start_script)}",
                cwd=self.server_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            log_thread = threading.Thread(target=self.read_stdout, args=(self.server_process,), daemon=True)
            log_thread.start()
            while self.server_process is not None:
                time_elapsed = timer() - start_time
                if self.server_state == ServerState.STARTING:
                    print(" │ MCSC.start │ Server is still booting...")
                    self.update_global_progress_msg(time_elapsed, self.average_boot_time)
                    await boot_message.edit(content=self.booting_progress_msg)
                elif self.server_state == ServerState.ON:
                    print(" │ MCSC.start │ Server is Online!")
                    self.update_global_progress_msg(time_elapsed, self.average_boot_time)
                    await boot_message.edit(content=self.booting_progress_msg)
                    self.update_boot_times(time_elapsed)
                    break
                await asyncio.sleep(1)
                
            if self.server_state == ServerState.STARTING:
                print(" │ MCSC.start │ Did the server crash?")       
                
        except Exception as e:
            self.server_state = ServerState.OFF
            print(e)
    
    #####################################################################################
    #                        Monitor and Log Server Output                              #
    #####################################################################################
    
    def read_stdout(self, server_process):
        with server_process.stdout:
            for line in iter(server_process.stdout.readline, ''):
                logging.info(line.strip())
                self.last_30_log.appendleft(line)
                if self.online_indicator in line:
                    print(" │ MCSC.read_stdout │ Server is ready!")
                    self.server_state = ServerState.ON
                if self.shutdown_indicator in line:
                    print(" │ MCSC.read_stdout │ Server Shutdown Detected.")
                    if self.server_state == ServerState.ON:
                        loop = asyncio.get_event_loop()
                        loop.create_task(self.ingame_shutdown())                        
                
    #####################################################################################
    #                      Manage the "booting" message                                 #
    #####################################################################################
                             
    async def synced_starting_msg(self, starting_message):
        await starting_message.edit(content=self.booting_progress_msg)
        while not (self.server_state == ServerState.ON):
            await asyncio.sleep(1)
            await starting_message.edit(content=self.booting_progress_msg)
        await starting_message.edit(content=self.booting_progress_msg)
    
    def update_boot_times(self, new_time):
        self.server_mob_info["boot_times"].append(new_time)
        with open(self.server_mob_info_path, "w") as file:
            json.dump(self.server_mob_info, file)
    
    def update_global_progress_msg(self, elapsed_time, prev_average_time):
        if self.server_state == ServerState.ON:
            percentage = 100
        else:
            if elapsed_time > prev_average_time:
                average_time = elapsed_time + 1
            else:
                average_time = prev_average_time
            percentage = (elapsed_time * 100) / average_time
        if prev_average_time == 0:
            prev_average_time = 'First time boot. No previous data to work with.'
        else:
            prev_average_time = self.format_time(prev_average_time)
        if percentage < 100:
            loading_bar = self.update_loading_bar(percentage)
            self.booting_progress_msg = f"```\n\
        ╔                              ╗\n\
█═╦═════╣     Server is Booting up     ║\n\
  ║     ╚                              ╝\n\
  ╠══│ Average Boot time: {prev_average_time}\n\
  ╠══│ Elapsed Time: {self.format_time(elapsed_time)}\n\
  ╚══│ {loading_bar} │ {percentage:.2f}%\n```"
        else:
            loading_bar = self.update_loading_bar(percentage)
            self.booting_progress_msg = f"```\n\
        ╔                              ╗\n\
█═╦═════╣       Server is Online       ║\n\
  ║     ╚                              ╝\n\
  ╠══│ Average Boot time: {prev_average_time}\n\
  ╠══│ Elapsed Time: {self.format_time(elapsed_time)}\n\
  ╠══│ {loading_bar} │ {percentage}%\n\
  ╚══│ Server is online at: {self.server_access_point}\n```"
    
    def format_time(self, time_to_format):
        if time_to_format < 60:           
            return f"{int(time_to_format)}s"
        else:
            return f"{int(time_to_format) // 60}m {int(time_to_format%60)}s"

    def update_loading_bar(self, progress):
        filled_amount = int(int(progress)/4)
        filled_ascii = '█'
        unfilled_amount = int(100/4) - filled_amount
        unfilled_ascii = '░'
        # print(f" │ MCSC.update_loading_bar │ Filled - Unfilled: {filled_amount} - {unfilled_amount}")
        return f"{filled_ascii * filled_amount}{unfilled_ascii * unfilled_amount}"

    #####################################################################################
    #                               Stop the server                                     #
    #####################################################################################


    async def stop(self, stop_message):
        if self.server_process is None:
            print(" │ MCSC.stop │ Server is not on")
            await stop_message.edit(content="Attempting to stop the server when there is no server process running, if you seee this let the dev know :)")
        try:
            self.server_state = ServerState.STOPPING
            stop_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣  Server is Shutting down  ║\n\
  ║     ╚                           ╝\n\
  ╚══│ Stopping server\n```"
            await stop_message.edit(content=stop_message_text)
            # Send the "stop" command to the server process
            self.server_process.stdin.write("stop\n")
            self.server_process.stdin.flush()
            await asyncio.sleep(2)
            while await self.check_recent_logs("All dimensions are saved") == None:
                await asyncio.sleep(2)
            # self.server_process.wait()
            stop_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣  Server is Shutting down  ║\n\
  ║     ╚                           ╝\n\
  ╠══│ Stopping server\n\
  ╚══│ Ending Process\n```"
            await stop_message.edit(content=stop_message_text)
            self.server_process = None
            self.server_state = ServerState.OFF
            stop_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣  Server is Shutting down  ║\n\
  ║     ╚                           ╝\n\
  ╠══│ Stopping server\n\
  ╠══│ Ending Process\n\
  ╚══│ Server is off. You can find this session's logs at: {os.path.basename(self.last_log_file)}\n```"
            await stop_message.edit(content=stop_message_text)
            print(" │ MCSC.stop │ Server turned off")
        except Exception as e:
            print(e)

    async def ingame_shutdown(self):
        self.server_state = ServerState.STOPPING
        self.server_process = None
        self.server_state = ServerState.OFF
        await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="you 👁️👄👁️"))
        print(" │ MCSC.ingame_shutdown │ Server turned off.")
          
    #####################################################################################
    #                           Check Connected Players                                 #
    #####################################################################################
                 
    async def connected_players(self):
        if self.server_process is None:
            print(" │ MCSC.connected_players │ Process is None.")
            return None
        else:
            self.server_process.stdin.write("list\n")
            self.server_process.stdin.flush()
            print(" │ MCSC.connected_players │ Entered list command.")
            await asyncio.sleep(0.25)
            players_online = await self.check_recent_logs("players online").split(":")[-1]
            print(f" │ MCSC.connected_players │ Found {len(players_online)} players online.")
            if len(players_online) == 0:
                return 0, None
            else:
                num_online = players_online.split(", ")
                players_online_str = ""
                for player in num_online:
                    players_online_str += f" {player}"
                return len(num_online), players_online_str

    async def check_recent_logs(self, search_value):
        print(f" │ MCSC.recent_logs │ Searching for {search_value}")
        for line in self.last_30_log:
            if search_value in line:
                print(f" │ MCSC.recent_logs │ Found {search_value} in the following line:\n │ MCSC.recent_logs │ - {line}")
                return line
        return None

    # def search_log(self, file_path, condition, chunk_size=1024):
    #     print("looking for", condition)
    #     with open(file_path, 'rb') as file:
    #         file.seek(0, os.SEEK_END)
    #         file_size = file.tell()
    #         buffer = b''
    #         position = file_size

    #         while position > 0:
    #             move_by = min(position, chunk_size)
    #             position -= move_by
    #             file.seek(position)

    #             chunk = file.read(move_by)
    #             buffer = chunk + buffer

    #             lines = buffer.split(b'\n')

    #             buffer = lines.pop(0)

    #             for line in reversed(lines):
    #                 if condition.encode() in line:
    #                     return line.decode().strip()
            
    #         if buffer and condition.encode() in buffer:
    #             return buffer.decode().strip()

    #     return None
                    
    def op(self):
        return
    
    def info(self):
        return
    
    async def list_logs(self, list_logs_message, last_x=None):
        all_log_names = os.listdir(self.log_dir)
        if last_x == None:
            last_x_logs = all_log_names
        elif len(all_log_names) > int(last_x):
            last_x_logs = all_log_names[-int(last_x):]
        else:
            last_x_logs = all_log_names
        last_x_logs.reverse()
        list_logs_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣       Existing Logs       ║\n\
  ║     ╚                           ╝\n"
        for index, name in enumerate(last_x_logs):
            if index != len(last_x_logs) - 1:
                list_logs_message_text += f"  ╠══│ {name}\n"
            else:
                list_logs_message_text += f"  ╚══│ {name}\n```"
        await list_logs_message.edit(content=list_logs_message_text)  

    async def get_log(self, channel, log_message, filename):
        if filename.lower() == 'latest':
            file_name = os.path.basename(self.last_log_file)
        else:
            file_name = filename
        log_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣           Logs            ║\n\
  ║     ╚                           ╝\n\
  ╚══│ Looking for log with the filename: {file_name}\n```"
        await log_message.edit(content=log_message_text)
        file_path = os.path.join(self.log_dir, file_name)
        if os.path.isfile(file_path):
            log_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣           Logs            ║\n\
  ║     ╚                           ╝\n\
  ╠══│ Looking for log with the filename: {file_name}\n\
  ╚══│ Requested file found.\n```"
            log_file = discord.File(file_path, filename=file_name)
            await log_message.edit(content=log_message_text)
            await channel.send(file=log_file)
        else:
            log_message_text = f"```\n\
        ╔                           ╗\n\
█═╦═════╣           Logs            ║\n\
  ║     ╚                           ╝\n\
  ╠══│ Looking for log with the filename: {file_name}\n\
  ╠══│ Requested file was not found.\n\
  ╠══│ If you want the most recent logs, the filename is {self.last_log_file}\n\
  ╚══│ Or try using [!mc list_logs] to get a list of the existing files.\n```"
            await log_message.edit(content=log_message_text)
            
    async def get_live_log_buffer(self, buffer_message):
        if self.last_30_log is not None:
            buffer_msg_txt= f"```\n\
        ╔                           ╗\n\
█═══════╣        Log Buffer         ║\n\
        ╚                           ╝\n"
            for line in reversed(self.last_30_log):
                buffer_msg_txt += f" │ {line}"
            buffer_msg_txt += "```"
            line_index = 1
            
            while len(buffer_msg_txt) > 2000:
                print(line_index)
                print(len(buffer_msg_txt))
                buffer_msg_txt= f"```\n\
        ╔                           ╗\n\
█═══════╣        Log Buffer         ║\n\
        ╚                           ╝\n"
                for line in itertools.islice(reversed(self.last_30_log), line_index, None):
                    buffer_msg_txt += f" │ {line}"
                buffer_msg_txt += "```"
                line_index += 1
            await buffer_message.edit(content=buffer_msg_txt)
        else:
            await buffer_message.edit(content="```\nThere are no active logs to retrieve.\n```")