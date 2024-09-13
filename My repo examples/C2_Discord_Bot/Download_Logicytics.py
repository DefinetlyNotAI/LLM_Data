import ctypes
from datetime import datetime
import colorlog
import requests
from zipfile import ZipFile
import io
import subprocess
import os
import shutil


class Log:
    def __init__(
            self,
            filename="C2.log",
            err_filename=None,
            use_colorlog=True,
            debug=False,
            debug_color="cyan",
            info_color="green",
            warning_color="yellow",
            error_color="red",
            critical_color="red",
            colorlog_fmt_parameters="%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",
    ):
        """
        Initializes a new instance of the LOG class.

        The log class logs every interaction when called in both colorlog and in the log File

        Best to only modify filename, and DEBUG.

        Only if you are planning to use the dual-log parameter that allows you to both log unto the shell and the log
        File: IMPORTANT: This class requires colorlog to be installed and also uses it in the INFO level, To use the
        DEBUG level, set DEBUG to True.

            If you are using colorlog, DO NOT INITIALIZE IT MANUALLY, USE THE LOG CLASS PARAMETER'S INSTEAD.
            Sorry for any inconvenience that may arise.

        Args: filename (str, optional): The name of the log File. Defaults to "Server.log". use_colorlog (bool,
        optional): Whether to use colorlog. Defaults to True. debug (bool, optional): Whether to use the DEBUG level.
        Defaults to False (which uses the INFO level). debug_color (str, optional): The color of the DEBUG level.
        Defaults to "cyan". info_color (str, optional): The color of the info level. Defaults to "green".
        warning_color (str, optional): The color of the warning level. Defaults to "yellow". error_color (str,
        optional): The color of the error level. Defaults to "red". critical_color (str, optional): The color of the
        critical level. Defaults to "red". colorlog_fmt_parameters (str, optional): The format of the log message.
        Defaults to "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s".

        Returns:
            None
        """
        self.level = debug
        self.color = use_colorlog
        if self.color:
            # Configure colorlog for logging messages with colors
            logger = colorlog.getLogger()
            if debug:
                logger.setLevel(
                    colorlog.DEBUG
                )  # Set the log level to DEBUG to capture all relevant logs
            else:
                logger.setLevel(
                    colorlog.INFO
                )  # Set the log level to INFO to capture all relevant logs
            handler = colorlog.StreamHandler()
            formatter = colorlog.ColoredFormatter(
                colorlog_fmt_parameters,
                datefmt=None,
                reset=True,
                log_colors={
                    "DEBUG": debug_color,
                    "INFO": info_color,
                    "WARNING": warning_color,
                    "ERROR": error_color,
                    "CRITICAL": critical_color,
                },
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        self.filename = str(filename)
        if err_filename is None:
            self.err_filename = self.filename
        else:
            self.err_filename = str(err_filename)
        if not os.path.exists(self.filename):
            self.__only("|" + "-" * 19 + "|" + "-" * 13 + "|" + "-" * 152 + "|")
            self.__only(
                "|     Timestamp     |  LOG Level  |"
                + " " * 70
                + "LOG Messages"
                + " " * 70
                + "|"
            )
            self.__only("|" + "-" * 19 + "|" + "-" * 13 + "|" + "-" * 152 + "|")

    @staticmethod
    def __timestamp() -> str:
        """
        Returns the current timestamp as a string in the format 'YYYY-MM-DD HH:MM:SS'.

        Returns:
            str: The current timestamp.
        """
        now = datetime.now()
        time = f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
        return time

    def __only(self, message):
        """
        Logs a quick message to the log File.

        Args:
            message: The message to be logged.

        Returns:
            None
        """
        with open(self.filename, "a") as f:
            f.write(f"{str(message)}\n")

    @staticmethod
    def __pad_message(message):
        """
        Adds spaces to the end of a message until its length is exactly 153 characters.

        Parameters:
        - message (str): The input message string.

        Returns:
        - str: The padded message with a length of exactly 153 characters.
        """
        # Calculate the number of spaces needed
        num_spaces = 151 - len(message)

        if num_spaces > 0:
            # If the message is shorter than 153 characters, add spaces to the end
            padded_message = message + " " * num_spaces
        else:
            # If the message is already longer than 153 characters, truncate it to the first 148 characters
            padded_message = message[:148]
            padded_message += "..."

        padded_message += "|"
        return padded_message

    def debug(self, message):
        """
        Logs an debug message via colorlog

        Args:
            message: The message to be logged.

        Returns:
            None
        """
        if self.level:
            colorlog.debug(message)

    def info(self, message):
        """
        Logs an informational message to the log File.

        Args:
            message: The message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.info(message)
        with open(self.filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > INFO:     | {self.__pad_message(str(message))}\n"
            )

    def warning(self, message):
        """
        Logs a warning message to the log File.

        Args:
            message: The warning message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.warning(message)
        with open(self.filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > WARNING:  | {self.__pad_message(str(message))}\n"
            )

    def error(self, message):
        """
        Logs an error message to the log File.

        Args:
            message: The error message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.error(message)
        with open(self.err_filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > ERROR:    | {self.__pad_message(str(message))}\n"
            )

    def critical(self, message):
        """
        Logs a critical message to the error log File.

        Args:
            message: The critical message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.critical(message)
        with open(self.err_filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > CRITICAL: | {self.__pad_message(str(message))}\n"
            )


log = Log(debug=False)


def Logicytics():
    """
    The main function of the Logicytics script.

    This function first checks if the script is running with administrative privileges.
    If not, it exits with an error message.

    Then, it downloads the Logicytics repository from GitHub and extracts it.
    It then changes to the extracted directory and runs the command "pip install -r requirements.txt"
    to install the necessary Python packages.

    After that, it changes to the CODE directory and runs the command
    "python .\\Logicytics.py --threaded" to execute the Logicytics script.

    Finally, it copies the ACCESS directory to the parent directory and prints a message indicating the
    success of the directory copy.

    This function does not take any parameters and does not return anything.
    """
    # Check if the script is running with administrative privileges
    if not ctypes.windll.shell32.IsUserAnAdmin():
        exit("Please run this script as an administrator.")

    url = "https://github.com/DefinetlyNotAI/Logicytics/archive/main.zip"
    response = requests.get(url)
    with ZipFile(io.BytesIO(response.content)) as zip_file:
        zip_file.extractall()
    
    # Install dependencies
    os.chdir(os.path.join(os.getcwd(), 'Logicytics-main'))

    try:
        result = subprocess.run("pip install -r requirements.txt", capture_output=True, text=True)
        log.debug(f"Installing dependencies: {result.stdout}")
    except subprocess.CalledProcessError as e:
        log.error(f"Error executing command: {e}")
        exit("Script has failed")
    except Exception as e:
        log.error(f"Error: {e}")
        exit("Script has failed")

    # Run Logicytics
    os.chdir(os.path.join(os.getcwd(), 'CODE'))

    try:
        result = subprocess.run("python .\\Logicytics.py --threaded", capture_output=True, text=True)
        log.debug(f"Executing Logicytics:\n {result.stderr}")
    except subprocess.CalledProcessError as e:
        log.error(f"Error executing command: Most likely invalid permissions: {e}")
        exit("Script has failed")
    except Exception as e:
        log.error(f"Error: {e}")
        exit("Script has failed")

    # Copy the ACCESS directory
    os.chdir(os.path.join(os.getcwd(), '..'))
    
    try:
        src_dir = r"ACCESS"
        dst_dir = r"..\ACCESS"
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        log.debug(f"Directory copied successfully from {src_dir} to {dst_dir}")
    except Exception as e:
        log.error(f"Error: {e}")
        exit("Script has failed")

    # Return to parent directory
    os.chdir(os.path.join(os.getcwd(), '..'))
