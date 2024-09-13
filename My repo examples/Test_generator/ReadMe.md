# Exam Generator Server Project Documentation


<div align="center">
    <a href="https://github.com/DefinetlyNotAI/Test_generator/issues"><img src="https://img.shields.io/github/issues/DefinetlyNotAI/Test_generator" alt="GitHub Issues"></a>
    <a href="https://github.com/DefinetlyNotAI/Test_generator/tags"><img src="https://img.shields.io/github/v/tag/DefinetlyNotAI/Test_generator" alt="GitHub Tag"></a>
    <a href="https://github.com/DefinetlyNotAI/Test_generator/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/t/DefinetlyNotAI/Test_generator" alt="GitHub Commit Activity"></a>
    <a href="https://github.com/DefinetlyNotAI/Test_generator/languages"><img src="https://img.shields.io/github/languages/count/DefinetlyNotAI/Test_generator" alt="GitHub Language Count"></a>
    <a href="https://github.com/DefinetlyNotAI/Test_generator"><img src="https://img.shields.io/github/repo-size/DefinetlyNotAI/Test_generator" alt="GitHub Repo Size"></a>
    <a href="https://codeclimate.com/github/DefinetlyNotAI/Test_generator/maintainability"><img src="https://api.codeclimate.com/v1/badges/31dde9ab1bb773ce9f31/maintainability" /></a>
</div>

## Table of Contents 🔍

- [Introduction](#introduction-)
- [Integration](#integration-)
- [Logging](#logging-information-)
- [File Formatting](#file-formats-)
  - [CSV](#csv-format-)
  - [JSON](#config-json-format-)
- [API Expectations](#database-expectations-api-)
  - [REC](#rec-api-)
  - [RUC](#ruc-api-)
  - [RUD](#rud-api-)
  - [RUR](#rur-api-)
- [Error Handling](#error-messages-)
- [Dependencies](#dependencies-)
- [License](#license-)
- [Contact](#contact-)

## Introduction 🌟

Exam Generator is a REST API backend service that generates exams for a given subject
and a given number of questions. The API is built using python and uses SQLite as the database.
Here's a brief overview of the project:

**DataBase.py**: This file contains the SQL class for the database operations. 
It uses SQLite3 to interact with the SQLite database. 
It also includes methods to create tables, insert data, update data, delete data, and query data.
it also contains the Database class, which represents a usage of the exam generation.
It has properties included in the `config.json` file. 
It is responsible for generating exams. 
It takes a subject and the number of questions as parameters,
and returns a list of randomly selected questions from the configuration file.

The API is designed to be scalable and can handle a large number of questions for each subject.
It also includes error handling and logging to ensure the smooth operation of the application.

The project is built using Python and SQLite as well as tiny amounts of PowerShell,
it uses SQLite as the database. The API is designed to be static - non-returning flag
and can be used with any frontend framework or application. 
The API is LOCAL - So only having the source code in your server allows the APIs Usage or having the EXE.

## Integration 🛠️

Integrating this project is super easy;

1) Move this whole directory to your server's directory
2) Make your server able to communicate and access `config.json` as well as the `DataBase.py` or `DataBase.exe`
3)  All the server needs to do is modify the `config.json` file to include required parameters, then execute `DataBase.py ` or `DataBase.exe`
4) Once executed a `Exam.xslx` file is produced, you can access it for you newly generated dataset
5) OPTIONAL: A `.log` is also generated, in case of errors, fallback to it



You must place the secret key in the first line in the file `cat` or else after August 31st the software will fail. I will post the key in the future.

The `DataBase.py` will not communicate back to you in any way, in case of errors it won't communicate.
Reason being this has been tested vigorously, and only fails if the end user/front-end fails
The file will however create a `ERROR.temp` file incase a user fault occurs, it will contain predetermined messages,
If you want to use this feature, you must include a check on your end for the `ERROR.temp` file, and delete it
after reading its contents, The list of pre-defined errors are [here](#error-messages-)

The same goes with `DataBase.exe` but you actually run it rather than import it, and you should run with admin privileges

## Logging Information 📝

Everything that occurs is logged to a special `.log` file, it contains everything, You cannot disable this feature!
It does a neat log that contains the following headers:-

- **Timestamp** Includes date and time of the log
- **LOG Level** Includes the log level, ranges from INFO, WARNING, ERROR, CRITICAL
- **Message** Includes the log message

It's all in a neat fashion, every time the software is re-opened anew, a special series of `-` appear to show
it's a new log, without deleting previous ones.

If debugging, the CLI will show special `colorlog` messages that include exact realtime logging.

## File Formats 📃

These will explain exactly the required formats, and tips on how to use them

### CSV Format 📃

This usually should be static and human-controlled

Each item must be separated by a comma, this produces a set, each set is separated by a new line,
An example of a `.csv` file;

```csv
Questions,Question Type,Difficulty (Easy, Medium, Hard),Score
q0001,t7,Easy,2
q0002,t3,Easy,1
q0003,t2,Medium,2
q0004,t2,Medium,2
q0005,t1,Easy,1
```

In each line, only 4 items are allowed based on the headers
`Questions, Question Type, Difficulty (Easy, Medium, Hard), Score`

You may also see it as `Data, Data Type, Action Difficulty, Weight` 
which is based on the application you are using

A maximum of 100 points can be given to a question!

The encoding should be `UTF-8`

### CONFIG JSON Format 👨‍💻

This should always change and be computer-controlled

In the `config.json` file, there are 10 keys:

- `hard_data_to_use`: Integer: Amount of question to be classified as hard.
- `medium_data_to_use`: Integer: Amount of question to be classified as medium.
- `easy_data_to_use`: Integer: Amount of question to be classified as easy.
- `minimum_titles`: Integer: The minimum amount of separate titles the exam should have. (For better chances of succeeding have it ~20% of total questions or else it results in impossible requests)
- `total_points`: Integer: Exact amount of points the generated data set should have.
- `use_debug_(ONLY_IF_YOU_DEVELOPED_THIS!)`: Boolean: DO NOT TAMPER.
- `api`: String: API type to use, refer to [this](#database-expectations-api-) part of the documentation.
- `username`: String: The USER that will be acted upon the database
- `password`: String: The USER's PASSWORD that will be acted upon the database
- `exclusion_titles`: List[String]: Titles you want to exclude from generation, this is very sensitive and CAN result in impossible requests

And the base file should look like this:

```json
{
      "hard_data_to_use": 2,
      "medium_data_to_use": 1,
      "easy_data_to_use": 3,
      "minimum_titles": 3,
      "total_points": 10,
      "use_debug_(ONLY_IF_YOU_DEVELOPED_THIS!)": true,
      "api": "",
      "username": "",
      "password": "",
      "exclusion_titles": [","]
}
```

The json file when read should always return a tuple of 10 items, 
in order `tuple[int, int, int, int, int, int, bool, str, str, str, list[str]]`

Not following the format will result in a false bool thrown, which results in an error.

Please note the harsher you are in the rules the more impossible requests error will generate, 
try to always have a ratio between given data (`.csv`) and rules.

To always make sure it will generate, try knowing the total questions you need (lets say 5) and go to your dataset, 
and use the first 5 to generate your configuration for yourself.

## Database Expectations API 🗂️

### REC API 🧠

Request Exam Creation

This will request to create an exam based on the users username and password,
It outputs an `.xslx` file

### RUC API 👤

Request User Creation

This will request creating a username with the provided password,
Saves to the `users.db`

Username MUST follow the following RegEx Pattern `^[a-zA-Z ]{3,30}$`
Password MUST follow the following RegEx Pattern `^[a-zA-Z0-9 _!?]{8,36}$`

### RUD API 🔝

Request User DB Update

This requests adding extra exclusion titles to the username provided, requires a password

### RUR API 🚫

Request User Removal

Requests to remove the user via the password given as well.

## Error Messages 🐛

In your end have a daemon thread that always checks if `ERROR.temp` exists, if it does, quickly read its contents (1 liner)
and delete the file.

The contents include:-
- **CS** - Corrupted Start - System files were corrupted or not found - No logs will generate - This is a crash
- **IC** - Incorrect Credentials - The user has inputted wrong username or password.
- **UKF** - Unknown Failure - A very broad error, Check the logs for the exact source - Requires human intervention
- **IAPI** - Invalid API - The config file's API is wrong and not part of the 4 [APIs](#database-expectations-api-)
- **CCD** - Corrupted Configuration Data - The configuration given is completely wrong and not valid - Check logs for further details
- **CNU** - Corrupted New User - The content given is `None` (Occurs only in RUC) - Check logs for further details
- **RGXF** - ReGeX Failure - The content given is failed to be validated by the ReGeX param, Due to the user inputting wrong data (Occurs only in RUC) - Check logs for further details
- **CP** - Common Password - The password given is common and not valid either due to it being blacklisted OR due to it already being used (Occurs only in RUC) - Check logs for further details

You may automate special web error messages based on those codes.

## Dependencies 📦

Just install the dependencies using:
```bash
pip install -r requirements.txt
```

No need to update them later on to mediate crash risks, 
but you may rerun the command to check for compatible newer versions.

```text
DateTime~=5.5
colorlog~=6.8.2
pandas~=2.2.2
```

You are advised to run this software in a separate python environment.

## License 📄

This project is licensed under the [MIT License](LICENSE). See the LICENSE file for details.

## Contact 📧

For inquiries or contributions, please contact Shahm Najeeb at my email `Nirt_12023@outlook.com`.
