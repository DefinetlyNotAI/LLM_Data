"""
Complexity:
    Time: BEST CASE: O(n+1) - WORST CASE: O(n^2)
        (Average time is usually 0.17ms for input size of 10,000 csv params and output of 6 params with precision of 100%)
        (Automatically 1 second is added to the time to make sure the sync is on (using `time.sleep`))

    Space: O(n)
        (Average RAM intake is around 0.32MB for input size of 10,000 (Excluding the .json and csv file sizes)
"""

import csv
import json
import os.path
import random
import re
import sqlite3
import hashlib
import os
import time
import colorlog
import pandas as pd
import datetime as dt
from datetime import datetime


class SQL:
    def __init__(self, database_name="Users.db"):
        """
        Initializes the SQL class.

        Args:
            database_name (str, optional): The name of the database. Defaults to "Users.db".
        """
        # Set the database name
        self.db_name = database_name
        if not os.path.exists(self.db_name):
            self.create_db()
        # Initialize the connection and cursor to None
        self.conn = None
        self.cursor = None

    def __connect(self):
        """
        Establishes a connection to the SQLite database.

        If a connection does not already exist, this method creates a new connection
        and sets the cursor object.
        """
        # Check if a connection has already been established
        if self.conn is None:
            colorlog.debug("Connecting to SQLite database...")
            # Create a new connection to the SQLite database
            self.conn = sqlite3.connect(self.db_name)
            # Set the cursor object for the connection
            self.cursor = self.conn.cursor()

    def __disconnect(self):
        """
        Closes the existing database connection and resets the connection and cursor objects.

        This method is used to disconnect from the SQLite database when it is no longer needed.
        """
        # Check if a connection has already been established
        if self.conn:
            colorlog.debug("Disconnecting from SQLite database...")
            # Close the existing connection to the SQLite database
            self.conn.close()
            # Reset the connection object to None
            self.conn = None
            # Reset the cursor object to None
            self.cursor = None

    def __add_exclusion_db(self, name: str, exclusion_titles: list[str]) -> bool | None:
        """
        Adds new titles to exclude for a user in the database.

        Args:
            name (str): The username of the user.
            exclusion_titles (list[str]): The titles to exclude.

        Returns:
            str: A success or error message.
        """
        try:
            self.__connect()
            try:
                # Execute a SELECT statement to get the existing titles to exclude for the user
                self.cursor.execute(
                    """SELECT titles_to_exclude FROM Users WHERE username=?""",
                    (name,),
                )
                result = self.cursor.fetchone()

                # If no result is found or the result is None, set initial_titles to "PLACEHOLDER"
                if result is None or result[0] is None:

                    initial_titles = "PLACEHOLDER"
                else:
                    initial_titles = result[0]

                # Strip the whitespace from the initial_titles
                current_titles = initial_titles.strip()

                # Convert current_titles and titles to sets for easier set operations
                current_titles_set = set(current_titles.split(","))
                titles_set = set(exclusion_titles)

                # Find the new titles to exclude
                new_titles_set = titles_set - current_titles_set

                # If there are new titles to exclude, update the titles_to_exclude field in the database
                if new_titles_set:

                    updated_titles = ",".join(list(new_titles_set))
                    self.cursor.execute(
                        """UPDATE Users SET titles_to_exclude = COALESCE(titles_to_exclude ||?, '') WHERE username =?""",
                        (updated_titles, name),
                    )
                    self.conn.commit()
                    log.info(f"Successfully updated titles for user {name}.")
                    return True
                else:
                    log.warning(f"No new titles to add for user {name}.")
                    return False

            except Exception as e:
                log.error(f"An error occurred while adding exclusion titles. as {e}")
                return False
        except Exception as e:
            log.error(f"An error occurred while adding exclusion titles. as {e}")
            return False

    def create_db(self):
        """
        Creates the initial database schema by dropping and recreating the 'Users' table.

        This method establishes a connection to the SQLite database, drops the 'Users' table if it exists,
        creates a new 'Users' table with the required columns, and then closes the connection.
        """
        colorlog.debug("Creating initial database schema...")
        # Establish a connection to the SQLite database
        conn = sqlite3.connect(self.db_name)
        # Create a cursor object for the connection
        cursor = conn.cursor()

        # Drop the 'Users' table if it exists
        cursor.execute("""DROP TABLE IF EXISTS Users;""")

        # Create a new 'Users' table with the required columns
        cursor.execute(
            """CREATE TABLE Users (
                            id INTEGER PRIMARY KEY,
                            username TEXT NOT NULL UNIQUE,
                            password TEXT NOT NULL,
                            titles_to_exclude TEXT);"""
        )

        # Commit the changes to the database
        conn.commit()
        # Close the connection to the database
        conn.close()

    def verify_password(self, username, password) -> bool:
        """
        Verifies the password for a given username.

        Args:
            username (str): The username to verify the password for.
            password (str): The password to verify.
        """
        try:
            colorlog.debug(f"Verifying password of {username}")
            # Establish a connection to the database
            self.__connect()

            # Query the database to retrieve the stored password for the given username
            self.cursor.execute(
                "SELECT password FROM Users WHERE username=?", (username,)
            )

            # Fetch the query result
            result = self.cursor.fetchone()

            # Close the database connection
            self.__disconnect()

            # Check if a result was found
            if result:
                # Extract the stored password from the result
                stored_password = result[0]

                # Compare the provided password with the stored password
                if password == stored_password:
                    # Return True if the passwords match
                    return True

            # Return False if no result was found or the passwords do not match
            return False
        except Exception as e:
            # Log any errors that occur during the verification process
            log.info(f"An error occurred while verifying the password. as {e}")
            # Return False if an error occurs
            return False

    def add_db(self, username, exclusion_titles, password) -> bool:
        """
        Creates a new database entry for a user.

        Args:
            username (str): The username for the new user.
            exclusion_titles (list): A list of titles to exclude.
            password (str): The password for the new user.
        """
        try:
            colorlog.debug(f"Creating database entry for {username}")
            # Connect to the database
            self.__connect()

            # Check if the username already exists
            self.cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            existing_user = self.cursor.fetchone()
            self.__disconnect()

            # Check if the username already exists
            if existing_user:
                log.warning(f"Username already exists: {username}")
                return False

            # Create a new database entry for the user
            self.__connect()
            self.cursor.execute(
                "INSERT INTO users (username, password) VALUES (?,?)",
                (username, password),
            )
            self.conn.commit()
            self.__disconnect()

            # Add exclusion titles to the database
            sql.add_exclusion_db(username, exclusion_titles, "CDB")

            log.info("Password Successfully Made")
            return True
        except Exception as e:
            # Return an error message if an exception occurs
            log.error(f"An error occurred while creating the database entry. as {e}")
            return False

    def remove_user(self, username: str) -> bool:
        """
        Removes a user from the database if the provided username and password match.

        Args:
            username (str): The username of the user to be removed.

        Returns:
            bool: A success for true or error for false.
        """
        try:
            colorlog.debug(f"Removing data for {username}")
            # Connect to the database
            self.__connect()

            # Check if the user exists
            self.cursor.execute("SELECT * FROM Users WHERE username=?", (username,))
            user_exists = self.cursor.fetchone()

            # Disconnect from the database
            self.__disconnect()

            if not user_exists:
                # Return an error message if the user does not exist
                log.warning(f"User does not exist: {username}")
                return False

            # Connect to the database again
            self.__connect()

            # Delete the user from the database
            self.cursor.execute("DELETE FROM Users WHERE username=?", (username,))
            self.conn.commit()

            # Disconnect from the database
            self.__disconnect()

            # Return a success message
            log.info(f"Successfully removed data for {username}")
            return True
        except Exception as e:
            # Return an error message if an exception occurs
            log.error(f"An error occurred while removing the database entry. as {e}")
            return False

    @staticmethod
    def add_exclusion_db(name, exclusion_titles, special=None) -> bool:
        """
        Adds an exclusion database with the given name, titles, and password.

        Args:
            name (str): The name of the exclusion database.
            exclusion_titles (list): A list of titles for the exclusion database.
            special (str, optional): A special parameter. Defaults to None.
        """
        colorlog.debug(f"Adding exclusion titles for {name}")
        try:

            # Attempt to add the exclusion database
            value = sql.__add_exclusion_db(name, exclusion_titles)

            # Check if the operation was successful
            if value is False:
                return False

            # If special is not provided, add a default value
            if not special:
                # Add a default value to the exclusion database
                msg = sql.__add_exclusion_db(name, [","])
                # Check if the operation was successful
                if msg is False:
                    return False

            # Return the result of the operation
            return value

        except Exception as e:
            # Return an error message if an exception occurs
            log.error(f"An error occurred while adding exclusion titles. as {e}")
            return False

    def get_excluded_titles(self, username) -> list[str] | bool:
        """
        Retrieves the excluded titles for a given username from the database.

        Args:
            username (str): The username to retrieve excluded titles for.
        """
        try:
            colorlog.debug(f"Retrieving excluded titles for {username}")
            # Establish a connection to the database
            self.__connect()

            # Execute a query to retrieve the excluded titles for the given username
            self.cursor.execute(
                """SELECT titles_to_exclude FROM Users WHERE username=?""", (username,)
            )

            # Fetch the result of the query
            result = self.cursor.fetchone()

            # Close the database connection
            self.__disconnect()

            # If a result was found, process it
            if result:
                # Split the result into a list of titles
                titles_list = result[0].split(",")

                # Strip any leading or trailing whitespace from each title
                titles_to_exclude = [title.strip() for title in titles_list]
            else:
                # If no result was found, return an empty list
                titles_to_exclude = []

            # Return the list of excluded titles
            return titles_to_exclude
        except Exception as e:
            # If an error occurs, return an error message
            log.error(f"An error occurred while retrieving excluded titles. as {e}")
            return False

    def password_exists(self, password) -> bool:
        """
        Checks if a given password exists anywhere in the database.

        Args:
            password (str): The password to check.

        Returns:
            bool: True if the password exists, False otherwise.
        """
        # Connect to the SQLite database
        self.__connect()

        # SQL query to find any user whose password matches the given password
        query = "SELECT COUNT(*) FROM Users WHERE password = ?"
        self.cursor.execute(query, (password,))

        # Fetch the result of the query
        count = self.cursor.fetchone()[0]

        # Close the database connection
        self.__disconnect()

        # Return True if the password exists (count > 0), False otherwise
        return count > 0


class LOG:
    def __init__(
        self,
        filename="Server.log",
        use_colorlog=True,
        DEBUG=False,
        debug_color="cyan",
        info_color="green",
        warning_color="yellow",
        error_color="red",
        critical_color="red",
        colorlog_fmt_parameters="%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",
    ):
        """
        Initializes a new instance of the LOG class.

        The log class logs every interaction when called in both colorlog and in the log file

        Best to only modify filename, and DEBUG.

        Only if you are planning to use the dual-log parameter that allows you to both log unto the shell and the log file:
            IMPORTANT: This class requires colorlog to be installed and also uses it in the INFO level,
            To use the debug level, set DEBUG to True.

            If you are using colorlog, DO NOT INITIALIZE IT MANUALLY, USE THE LOG CLASS PARAMETER'S INSTEAD.
            Sorry for any inconvenience that may arise.

        Args:
            filename (str, optional): The name of the log file. Defaults to "Server.log".
            use_colorlog (bool, optional): Whether to use colorlog. Defaults to True.
            DEBUG (bool, optional): Whether to use the debug level. Defaults to False (which uses the INFO level).
            debug_color (str, optional): The color of the debug level. Defaults to "cyan".
            info_color (str, optional): The color of the info level. Defaults to "green".
            warning_color (str, optional): The color of the warning level. Defaults to "yellow".
            error_color (str, optional): The color of the error level. Defaults to "red".
            critical_color (str, optional): The color of the critical level. Defaults to "red".
            colorlog_fmt_parameters (str, optional): The format of the log message. Defaults to "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s".

        Returns:
            None
        """
        self.color = use_colorlog
        if self.color:
            # Configure colorlog for logging messages with colors
            logger = colorlog.getLogger()
            if DEBUG:
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
        if not os.path.exists(self.filename):
            self.__only("|" + "-" * 19 + "|" + "-" * 13 + "|" + "-" * 154 + "|")
            self.__only(
                "|     Timestamp     |  LOG Level  |"
                + " " * 71
                + "LOG Messages"
                + " " * 71
                + "|"
            )
        self.__only("|" + "-" * 19 + "|" + "-" * 13 + "|" + "-" * 154 + "|")

    @staticmethod
    def __timestamp() -> str:
        """
        Returns the current timestamp as a string in the format 'YYYY-MM-DD HH:MM:SS'.

        Returns:
            str: The current timestamp.
        """
        now = datetime.now()
        timestamped = f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
        return timestamped.encode('utf-8').decode('utf-8')

    def __only(self, message):
        """
        Logs a quick message to the log file.

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
        num_spaces = 153 - len(message)

        if num_spaces > 0:
            # If the message is shorter than 153 characters, add spaces to the end
            padded_message = message + " " * num_spaces
        else:
            # If the message is already longer than 153 characters, truncate it to the first 153 characters
            padded_message = message[:150]
            padded_message += "..."

        padded_message += "|"
        return padded_message

    def info(self, message):
        """
        Logs an informational message to the log file.

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
        Logs a warning message to the log file.

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
        Logs an error message to the log file.

        Args:
            message: The error message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.error(message)
        with open(self.filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > ERROR:    | {self.__pad_message(str(message))}\n"
            )

    def critical(self, message):
        """
        Writes a critical message to the log file.

        Args:
            message: The critical message to be logged.

        Returns:
            None
        """
        if self.color:
            colorlog.critical(message)
        with open(self.filename, "a") as f:
            f.write(
                f"[{self.__timestamp()}] > CRITICAL: | {self.__pad_message(str(message))}\n"
            )



class DATABASE:
    def __init__(self):
        """
        Initializes the database.

        This method checks if the "users.db" file exists. If it doesn't, it logs a message and creates
        the database using the `sql.create_db()` function.

        It also checks if the "cat" and ".core/.ps1" files exist. If any of them are missing, it exits
        the program with an error message.

        Additionally, it checks if the size of the ".core/.ps1", "cat", and ".core/.py" files is zero.
        If any of them are empty, it exits the program with an error message.

        Finally, it logs a success message.

        Returns:
            None
        """
        if not os.path.exists("users.db"):
            colorlog.debug("Creating user database from scratch using SQLite")
            sql.create_db()
        log.info("Database loaded successfully.")

    @staticmethod
    def __error(error):
        """
        Logs an error message to the log file.

        Returns:
            None
        """
        if os.path.exists("ERROR.temp"):
            os.remove("ERROR.temp")
        with open("ERROR.temp", "w") as f:
            f.write(error)

    @staticmethod
    def __read_config() -> tuple[int, int, int, int, int, int, bool, str, str, str, list[str]] | bool:
        """
        Reads the configuration from the 'config.json' file and returns a tuple of the configuration parameters.

        Returns:
            A tuple containing the configuration parameters if the file is valid, otherwise False.
        """
        try:
            # Load the configuration from the JSON file
            with open("config.json") as f:
                config = json.load(f)

            # Extract the configuration parameters
            min_titles = config["minimum_titles"]
            hard = config["hard_data_to_use"]
            med = config["medium_data_to_use"]
            easy = config["easy_data_to_use"]
            points = config["total_points"]
            debug = config["use_debug_(ONLY_IF_YOU_DEVELOPED_THIS!)"]
            api = config["api"]
            username = config["username"]
            password = config["password"]
            exclusion_titles = config["exclusion_titles"]

            # Calculate the total number of questions
            questions_amount = hard + med + easy

            # Check if the configuration parameters are valid
            if (
                    isinstance(questions_amount, int)
                    and isinstance(min_titles, int)
                    and isinstance(hard, int)
                    and isinstance(med, int)
                    and isinstance(easy, int)
                    and isinstance(points, int)
                    and isinstance(debug, bool)
                    and isinstance(api, str)
                    and isinstance(username, str)
                    and isinstance(password, str)
                    and isinstance(exclusion_titles, list)
            ):
                return (
                    questions_amount,
                    min_titles,
                    hard,
                    med,
                    easy,
                    points,
                    debug,
                    api,
                    username,
                    password,
                    exclusion_titles,
                )
            else:

                log.critical("Invalid config file parameters.")
                return False
        except FileNotFoundError as fnfe:

            log.critical(f"File not found: {fnfe}")
            return False
        except Exception as e:

            log.error(f"Unexpected error: {e}")
            return False

    @staticmethod
    def __read_csv() -> list[list[str]] | bool:
        """
            Reads a CSV file and returns a list of questions.

            The CSV file is expected to have the following structure:
            - Each row represents a question.
            - The first row is ignored (header).
            - The second column represents the difficulty level.
            - The third column represents the score.
            - The fourth column represents the URL (optional).

            Returns:
                list[list[str]]: A list of questions, where each question is a list of strings.
                bool: False if an error occurs.
            """
        try:
            # Log a debug message to indicate that the CSV file is being read
            colorlog.debug("Reading CSV file...")

            # Initialize an empty list to store the questions
            questions = []

            # Open the CSV file in read mode with UTF-8 encoding
            with open("Data.csv", mode="r", encoding="utf-8") as file:
                # Create a CSV reader object
                reader = csv.reader(file)

                # Ignore the header row
                next(reader)

                # Iterate over each row in the CSV file
                for row in reader:
                    # Initialize an empty list to store the indices of columns to check
                    indices_to_check = []

                    # Iterate over each column index
                    for i in range(len(row)):
                        # If the column index is not the URL column, add it to the list of indices to check
                        if i != 4:
                            indices_to_check.append(i)

                    # Check if all values in the columns to check are non-empty
                    if not all(
                            value.strip()
                            for value in (row[i] for i in indices_to_check)
                    ):
                        # Log a critical error message if an empty value is found
                        log.critical("Empty value found in CSV.")
                        return False

                    # Extract the difficulty level from the second column
                    difficulty = row[2].strip()

                    # Check if the difficulty level is valid
                    if difficulty not in ["Hard", "Medium", "Easy"]:
                        # Log a critical error message if the difficulty level is invalid
                        log.critical(
                            f"Invalid difficulty level: {difficulty} at line {reader.line_num}."
                        )
                        return False

                    # Try to extract the score from the third column
                    try:
                        score = int(row[3].strip())
                    except ValueError:
                        # Log a critical error message if the score is not an integer
                        log.critical(
                            f"Invalid score format at line {reader.line_num}: {row[3]}."
                        )
                        return False

                    # Check if the score is within the valid range
                    if not 0 <= score <= 100:
                        # Log a critical error message if the score is out of range
                        log.critical(
                            f"Invalid score range at line {reader.line_num}: {score}."
                        )
                        return False

                    # Extract the URL from the fourth column (if present)
                    url_column_index = 4
                    url = (
                        row[url_column_index].strip()
                        if url_column_index < len(row)
                        else None
                    )

                    # Add the question to the list of questions
                    questions.append([*row[:url_column_index], url])

            # Return the list of questions
            return questions

        except FileNotFoundError as fnfe:
            # Log a critical error message if the file is not found
            log.critical(f"File not found: {fnfe}")
            return False

        except Exception as e:
            # Log an error message if an unexpected error occurs
            log.error(f"Unexpected error: {e}")
            return False

    def __generate_data(self, questions, exclude_list) -> tuple[
                                                              list[list[str]], int, dict[str, float], list[str]] | bool:
        """
            Generate exam data based on the provided questions and exclude list.

            Args:
            questions (list): A list of questions to generate the exam from.
            exclude_list (list): A list of titles to exclude from the exam.

            Returns:
            tuple: A tuple containing the generated exam, total points, difficulty ratios, and total titles.
            """
        try:
            # Continue generating exam data until a valid exam is created
            while True:
                # If no questions are provided, read from the CSV file
                if not questions:
                    questions = self.__read_csv()
                    if questions is False:
                        # Return False if reading from CSV fails
                        return False

                # Initialize exam data
                exam = []
                total_points = 0
                total_titles = []
                difficulty_counts = {"Hard": 0, "Medium": 0, "Easy": 0}

                # Extract excluded titles from the exclude list
                excluded_titles = [
                    title.strip() for title in exclude_list[0].split(",")
                ]

                # Filter out questions with excluded titles
                filtered_data = [
                    q for q in questions if q[1] not in excluded_titles
                ]

                # Generate exam questions
                for i in range(TOTAL_DATA_AMOUNT):
                    # If no more questions are available, break the loop
                    if not filtered_data:
                        break

                    # Determine the difficulty level
                    if i < HARD_DATA_AMOUNT:
                        difficulty = "Hard"
                    elif i < HARD_DATA_AMOUNT + MEDIUM_DATA_AMOUNT:
                        difficulty = "Medium"
                    else:
                        difficulty = "Easy"

                    # Select a random question
                    selected_question_index = random.randint(
                        0, len(filtered_data) - 1
                    )
                    selected_question = filtered_data[selected_question_index]

                    # Check if the question meets the criteria
                    if (
                            selected_question not in exam
                            and selected_question[2] == difficulty
                    ):
                        # Add the question to the exam
                        exam.append(selected_question)
                        total_points += int(selected_question[3])
                        difficulty_counts[selected_question[2]] += 1
                        filtered_data.pop(selected_question_index)
                        title_value = selected_question[1]
                        if title_value not in total_titles:
                            total_titles.append(title_value)

                # Check if the exam meets the requirements
                if len(exam) != TOTAL_DATA_AMOUNT:
                    continue

                # Calculate difficulty ratios
                total_difficulties = sum(difficulty_counts.values())
                if total_difficulties == 0:
                    # Return False if no difficulties are found
                    return False

                difficulty_ratios = {
                    k: v / total_difficulties * 100
                    for k, v in difficulty_counts.items()
                }

                # Check if the total points and titles meet the requirements
                if total_points != TOTAL_POINTS:
                    continue
                if len(total_titles) < MINIMUM_TYPES:
                    continue

                # Break the loop if a valid exam is created
                break

            # Return the generated exam data
            return exam, total_points, difficulty_ratios, total_titles
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Unexpected error: {e}")
            return False

    @staticmethod
    def __create_excel() -> bool:
        """
            Creates an Excel file from a text file and saves it as an Excel file.

            Returns:
                bool: True if the Excel file is created successfully, False otherwise.
            """
        try:
            # Initialize an empty list to store the data
            data = []

            # Set the headers for the Excel file based on the DEBUG_DB flag
            if DEBUG_DB:
                headers = ["URL", "Data", "Type", "Range", "Weight"]
            else:
                headers = ["URL", "Data", "Weight"]

            # Read the lines from the text file
            with open("Exam.txt", "r") as file:
                lines = file.readlines()

                # Iterate over the lines and extract the relevant data
                for i, line in enumerate(lines):
                    if i % 2 != 0:
                        continue

                    parts = line.strip().split("&")

                    # Check if the number of parts matches the expected length based on the DEBUG_DB flag
                    if DEBUG_DB and len(parts) == 5:
                        data.append(parts)
                    elif not DEBUG_DB and len(parts) == 3:
                        data.append(parts)

            # Create a DataFrame from the data and set the headers
            df = pd.DataFrame(data, columns=headers)

            # Save the DataFrame as an Excel file
            df.to_excel("Exam.xlsx", index=False)

            # Remove the original text file
            os.remove("Exam.txt")

            return True
        except FileExistsError as fnfe:
            # Log an error if the text file is not found
            log.critical(f"File not found: {fnfe}")
            return False
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Unexpected error: {e}")
            return False

    @staticmethod
    def __common(password) -> bool:
        """
        Checks if a given password is common or not.

        Args:
        password (str): The password to check.

        Returns:
        bool: True if the password is common, False otherwise.
        """
        common = [
            "password",
            "qwertyuiop",
            "12345678",
            "123456789",
            "1234567890",
            "qwerty",
            "password",
            "11111111",
            "123454321",
            "abcd?1234",
            "qwer!5678",
            "football",
            "springfield",
            "jessica",
            "jennifer",
            "princess",
            "superman",
            "iloveyou",
            "babygirl",
            "trustno1",
            "computer",
            "p@ssw0rd",
            "qwe123456",
            "qweasd123",
            "qwe123asd",
            "123qweasd",
            "p@ssword",
            "123qweasd",
            "123qwe123",
            "1q2w3e",
            "1q2w3e4r",
            "1q2w3e4r5t",
            "1q2w3e4r5t6y",
            "qwertyui",
            "asdfghjk",
            "asdfghjkl",
            "passw0rd",
        ]
        if password.upper() in common:
            return True
        elif password.lower() in common:
            return True
        return False

    def __exam_generator(self, username) -> bool:
        """
        Generates an exam based on the provided username.

        Args:
            username (str): The username of the user for whom the exam is being generated.

        Returns:
            bool: True if the exam is generated successfully, False otherwise.
        """

        # Read the CSV file containing the exam questions
        questions = self.__read_csv()
        if questions is False:
            # If the CSV file is not read successfully, return False
            return False

        try:
            # Get the excluded titles for the user
            Exclude_list = sql.get_excluded_titles(username)
            if Exclude_list is False:
                # If the excluded titles are not retrieved successfully, return False
                return False

            # Generate the exam data based on the questions and excluded titles
            temp = self.__generate_data(questions, Exclude_list)
            if temp is False:
                # If the exam data is not generated successfully, return False
                return False
            else:
                # Unpack the exam data into separate variables
                exam, total_points, difficulty_ratios, total_titles = temp

            # Check if the Exam.txt file already exists and remove it if it does
            if os.path.exists("Exam.txt"):
                os.remove("Exam.txt")

            # Write the exam data to the Exam.txt file
            with open("Exam.txt", "w") as file:
                # Check if debug mode is enabled
                if DEBUG_DB:
                    # Write a debug message to the file
                    file.write("Debug mode is on.\n\n")

                    # Write the exam data to the file in debug format
                    for sublist in exam:
                        file.write(
                            f"{sublist[4]} & {sublist[0]} & Type: {sublist[1]} & Difficulty: {sublist[2]} & [{sublist[3]}]\n"
                        )
                        file.write(
                            f"{sublist[4]} & {sublist[0]} & Type: {sublist[1]} & Difficulty: {sublist[2]} & [{sublist[3]}]\n"
                        )
                else:

                    # Write the exam data to the file in normal format
                    for sublist in exam:
                        file.write(f"{sublist[4]} & {sublist[0]} & [{sublist[3]}]\n")
                        file.write(f"{sublist[4]} & {sublist[0]} & [{sublist[3]}]\n")

                # Write the total points to the file
                file.write(f"\n\nTotal exam is out of {TOTAL_POINTS} points.")

            # Pause for 1 second
            time.sleep(1)

            # Create an Excel file based on the exam data
            msg = self.__create_excel()
            if msg is False:
                # If the Excel file is not created successfully, return False
                return False

            # Log the exam generation information
            log.info("Exam Generated and saved to Exam.xlsx")
            colorlog.debug("Exam Generation information:")
            colorlog.debug(f"Total Points in exam: {total_points}")
            colorlog.debug(f"Number of Questions Included in exam: {len(exam)}")
            colorlog.debug(f"Total Titles Used in exam: {len(total_titles)}")
            colorlog.debug(
                f"Difficulty Ratio used: Hard: {round(difficulty_ratios['Hard'], 2)}%, Medium: {round(difficulty_ratios['Medium'], 2)}%, Easy: {round(difficulty_ratios['Easy'], 2)}%"
            )
            return True
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Unexpected error: {e}")
            return False

    def api(self):
        """
        Handles API requests based on the provided configuration data.

        Returns:
        bool: True if the API request is successful, False otherwise.
        """
        try:
            # Read configuration data from the config file
            config_data = self.__read_config()

            # If config data is False, return False
            if config_data is False:
                self.__error("CCD")
                exit("Failed to read config file")

            # Unpack config data into global variables
            global TOTAL_DATA_AMOUNT, MINIMUM_TYPES, HARD_DATA_AMOUNT, MEDIUM_DATA_AMOUNT, EASY_DATA_AMOUNT, TOTAL_POINTS, DEBUG_DB
            (
                TOTAL_DATA_AMOUNT,
                MINIMUM_TYPES,
                HARD_DATA_AMOUNT,
                MEDIUM_DATA_AMOUNT,
                EASY_DATA_AMOUNT,
                TOTAL_POINTS,
                DEBUG_DB,
                API,
                USERNAME,
                PASSWORD,
                EXCLUDE,
            ) = config_data

            # Handle different API requests
            if API == "REC":
                # Request to generate an exam
                log.info(
                    f"A request has been made to generate an exam by the user {USERNAME}"
                )
                if sql.verify_password(USERNAME, PASSWORD):
                    # Generate exam and log result
                    if self.__exam_generator(USERNAME):
                        log.info("Exam generated successfully based on the request")
                    else:
                        log.error("Failed to generate exam")
                        self.__error("UKF")
                else:
                    self.__error("IC")
                    log.error("Wrong password given")

            elif API == "RUC":
                # Request to create a new user
                username_regex = r"^[a-zA-Z ]{3,30}$"
                password_regex = r"^[a-zA-Z0-9 _!?]{8,36}$"

                # Validate username and password
                if re.match(username_regex, USERNAME):
                    if re.match(password_regex, PASSWORD):
                        # Check if password is common or already exists
                        if not self.__common(PASSWORD) and not sql.password_exists(PASSWORD):
                            log.info(
                                f"A request has been made to create a new user by the following username {USERNAME}"
                            )
                            # Add user to database and log result
                            if sql.add_db(USERNAME, ["Title1", "Title2"], PASSWORD):
                                log.info("User created successfully based on the request")
                            else:
                                log.error(f"Failed to create user {USERNAME}")
                        else:
                            log.warning("Invalid password - Password is commonly used")
                    else:
                        log.warning(
                            "Invalid password - Password must be between 8 and 36 characters and contain at least one special character"
                        )
                else:
                    log.warning(
                        "Invalid username - Username must be between 3 and 30 characters and contain only letters and spaces"
                    )

            elif API == "RDU":
                if sql.verify_password(USERNAME, PASSWORD):
                    # Request to add exclusion titles to the database
                    log.info(
                        f"A request has been made to add the following exclusion titles {EXCLUDE} to the database for user {USERNAME}"
                    )
                    # Add exclusion titles to database and log result
                    if sql.add_exclusion_db(USERNAME, EXCLUDE):
                        log.info("Exclusion titles added successfully based on the request")
                    else:
                        log.error("Failed to add exclusion titles to database")
                        self.__error("UKF")
                else:
                    self.__error("IC")
                    log.error("Wrong password given")

            elif API == "RUR":
                if sql.verify_password(USERNAME, PASSWORD):
                    # Request to remove a user from the database
                    log.info(
                        f"A request has been made to remove the user {USERNAME} from the database"
                    )
                    # Remove user from database and log result
                    if sql.remove_user(USERNAME):
                        log.info("User removed successfully based on the request")
                    else:
                        log.error(f"Failed to remove {USERNAME} from database")
                        self.__error("UKF")
                else:
                    self.__error("IC")
                    log.error("Wrong password given")

            else:
                log.error(f"Invalid API inputted: {API}")
                self.__error("IAPI")

        except Exception as e:
            # Log any unexpected errors
            log.error(f"Unexpected error occurred: {e}")
            self.__error("UKF")



if __name__ == "__main__":
    db_name = "Users.db"
    sql = SQL(database_name=db_name)
    log = LOG(filename="DataBase.log")
    DATABASE().api()
