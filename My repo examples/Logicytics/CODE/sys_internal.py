from __lib_actions import *
from __lib_log import Log

sys_internal_executables = [
    "psfile.exe",
    "PsGetsid.exe",
    "PsInfo.exe",
    "pslist.exe",
    "PsLoggedon.exe",
    "psloglist.exe",
]


def sys_internal():
    """
    This function runs a series of system internal sys_internal_executables and logs their output.

    It iterates over a list of executable names, constructs the command to run each one,
    captures the output, and writes it to a file named 'SysInternal.txt'.

    The function also logs information and warning messages for each executable,
    including any errors that occur during execution.
    """
    with open("SysInternal.txt", "a") as outfile:
        # Iterate over each executable
        for executable in sys_internal_executables:
            try:
                # Construct the command to run the executable
                command = f"{os.path.join('SysInternal_Suite', executable)}"

                # Execute the command and capture the output
                result = subprocess.run(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                # Write the output to the File
                outfile.write("-" * 190)
                outfile.write(f"{executable} Output:\n{result.stdout.decode()}")
                log.info(f"{executable}: Successfully executed")

                # Optionally, handle errors if any
                if (
                    result.stderr.decode() != ""
                    and result.returncode != 0
                    and result.stderr.decode() is not None
                ):
                    log.warning(f"{executable}: {result.stderr.decode()}")
                    outfile.write(f"{executable}:\n{result.stderr.decode()}")

            except Exception as e:
                log.error(f"Error executing {executable}: {str(e)}")
                outfile.write(f"Error executing {executable}: {str(e)}\n")
    log.info("SysInternal: Successfully executed")


def check_sys_internal_dir() -> tuple[bool, bool]:
    if os.path.exists("SysInternal_Suite"):
        return any(
            os.path.exists(f"SysInternal_Suite/{file}")
            for file in sys_internal_executables
        ), os.path.exists("SysInternal_Suite/SysInternal_Suite.zip")
    else:
        log.error(
            "SysInternal_Suite cannot be found as a directory, force closing the sys_internal.py program, continuing Logicytics"
        )
        return False, False


log = Log(debug=DEBUG)
if check_sys_internal_dir()[0]:
    sys_internal()
elif check_sys_internal_dir()[0] is False and check_sys_internal_dir()[1] is True:
    log.warning(
        "Files are not found, They are still zipped, most likely due to a .ignore file being present, continuing Logicytics"
    )
elif check_sys_internal_dir()[0] is False and check_sys_internal_dir()[1] is False:
    log.error(
        "Files are not found, The zip file is also missing!, continuing Logicytics"
    )
