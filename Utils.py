import getpass
import json
import os
import psutil
import signal


DataDir = os.path.join(
    "/Users/{}/Library".format(getpass.getuser()), "Hallucinate")
HallucinateVersion = "v1.1"


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
        with open(os.path.join(r"/Users/Shared/Riot Games/", "RiotClientInstalls.json"), "r") as f:
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
