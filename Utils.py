import getpass
import json
import os
import platform
import psutil
import signal
import sys


if platform.system() == "Darwin":
    DataDir = os.path.join(
        "/Users/{}/Library".format(getpass.getuser()), "Hallucinate")
else:
    DataDir = os.path.join(
        "C:/Users/{}/Downloads".format(getpass.getuser()), "Hallucinate")
HallucinateVersion = "v1.1"


def sigint_handler(signal, frame):
    sys.exit(0)


def GetProcesses():
    riotCandidates = []
    for proc in psutil.process_iter():
        try:
            processName = proc.name()
            processID = proc.pid
            if processID != os.getpid() and processName == "LoR" or processName == "LeagueClient" or processName == "RiotClientServices":
                riotCandidates.append((processName, processID))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return riotCandidates


def IsClientRunning():
    return len(GetProcesses()) > 0


def KillProcesses():
    for process in GetProcesses():
        os.kill(process[1], signal.SIGKILL)


def GetRiotClientPath():
    try:
        rc_paths = []
        if platform.system() == "Darwin":
            abs_path = r"/Users/Shared/Riot Games/"
        else:
            abs_path = r"C:\\ProgramData\\Riot Games\\"
        with open(os.path.join(abs_path, "RiotClientInstalls.json"), "r") as f:
            install_locations = json.load(f)
            if "rc_default" in install_locations:
                rc_paths.append(install_locations["rc_default"])
            if "rc_live" in install_locations:
                rc_paths.append(install_locations["rc_live"])
            if "rc_beta" in install_locations:
                rc_paths.append(install_locations["rc_beta"])
        for path in rc_paths:
            return path
        return None
    except Exception as e:
        print(e)
        return None


KillProcesses()
