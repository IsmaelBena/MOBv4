import subprocess
import platform

def test_connection(host="8.8.8.8", count=1):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    
    command = ["ping", param, str(count), host]
    
    try:
        output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        print(output.stdout)

        if platform.system().lower() == "windows":
            for line in output.stdout.split("\n"):
                if "Average" in line:
                    latency = line.split()[-1].replace("ms", "")
                    return int(latency)
        else:
            for line in output.stdout.split("\n"):
                if "time=" in line:
                    latency = line.split("time=")[1].split(" ")[0]
                    return int(latency)
    except Exception as e:
        print(f"Failed to ping host: {e}")

    return None