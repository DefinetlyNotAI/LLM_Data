from __lib_actions import *
from __lib_log import Log


def wmic():
    """
    Retrieves system information using WMIC commands.

    This function runs a series of WMIC commands to gather information about the system's BIOS,
    operating system, computer system, and disk drives.
    The output of each command is written to a file named "wmic_output.txt".

    Parameters:
    None

    Returns:
    None
    """
    data = Actions.run_command("wmic BIOS get Manufacturer,Name,Version /format:htable")
    open("WMIC.html", "w").write(data)
    wmic_commands = [
        "wmic os get Caption,CSDVersion,ServicePackMajorVersion",
        "wmic computersystem get Model,Manufacturer,NumberOfProcessors",
        "wmic BIOS get Manufacturer,Name,Version",
        "wmic diskdrive get model,size",
    ]
    with open("wmic_output.txt", "w") as file:
        for i in range(len(wmic_commands)):
            log.info(f"Executing Command Number {i + 1}: {wmic_commands[i]}")
            output = Actions.run_command(wmic_commands[i])
            file.write("-" * 190)
            file.write(f"Command {i + 1}: {wmic_commands[i]}\n")
            file.write(output)

        file.write("-" * 190)


log = Log(debug=DEBUG)
wmic()
