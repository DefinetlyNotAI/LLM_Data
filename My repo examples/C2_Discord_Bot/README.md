# C2 Discord Bot 📎


Welcome to C2 Bot 🌐,
a cutting-edge tool
designed to allow you to control device using a discord bot and a vulnerable target.
Crafted with python,
it's an actively developed project that is
aimed at testing and learning.
This comprehensive guide is here to equip you with everything you need to use the bot effectively.

<div align="center">
    <a href="https://github.com/DefinetlyNotAI/C2_Discord_Bot/issues"><img src="https://img.shields.io/github/issues/DefinetlyNotAI/C2_Discord_Bot" alt="GitHub Issues"></a>
    <a href="https://github.com/DefinetlyNotAI/C2_Discord_Bot/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/t/DefinetlyNotAI/C2_Discord_Bot" alt="GitHub Commit Activity"></a>
    <a href="https://github.com/DefinetlyNotAI/C2_Discord_Bot/languages"><img src="https://img.shields.io/github/languages/count/DefinetlyNotAI/C2_Discord_Bot" alt="GitHub Language Count"></a>
    <a href="https://github.com/DefinetlyNotAI/C2_Discord_Bot/actions"><img src="https://img.shields.io/github/check-runs/DefinetlyNotAI/C2_Discord_Bot/main" alt="GitHub Branch Check Runs"></a>
    <a href="https://github.com/DefinetlyNotAI/C2_Discord_Bot"><img src="https://img.shields.io/github/repo-size/DefinetlyNotAI/C2_Discord_Bot" alt="GitHub Repo Size"></a>
    <a href="https://codeclimate.com/github/DefinetlyNotAI/C2_Discord_Bot/maintainability"><img src="https://api.codeclimate.com/v1/badges/cca8650d94930ae7382f/maintainability" /></a>
</div>

## 📜 Introduction

### 🪟 Overview

A bot that is the structure for C2 attacks, Its considered a backdoor where after implementing it
and giving it privileges you can control it via discord reactions

### 📖 Purpose

The primary aim of this project is to simplify
the process of implementing and creating backdoors
for educational and cybersecurity purposes.
By automating these tasks, users can focus more on analysis rather than manual processing.

## 📦 Installation

### 📄 Prerequisites

- Python 3.x installed.
- Access to the Discord Developer Portal.
- Basic knowledge of Discord bot development.
- Ability to actually seed in the backdoor

### 🪜 Steps to Install

In the victim side
1. Clone the repository or download the Discord bot script.
2. Place the `c2.py` script in a suitable location on their Windows computer.
3. Modify the `api.json` with your details
4. Configure the script to start automatically on boot with admin permissions.

## 🛠️ Configuration

Discord Bot Creation
1. Visit the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application and add a bot to it.
3. Make sure the bot has these permissions when creating it:
   - Administrator
4. Make sure all the intents in the `intents` section are enabled, these are found in the `oauth2` section.
5. Make sure the bot is added to the server you want to interact with.
6. Navigate to the bot page and copy the bot token. This token will be used later.

Account Activation
1. Activate your Discord account for developer mode to access channel IDs.
2. Go to your account's settings and navigate to the "Advanced" tab.
3. Enable "Developer Mode" and click "Save Changes".
4. Go to your 2 channels in your server and copy the channel IDs of a channel where commands should be sent (for security reasons make it a public restricted channel where only mods can talk in it) and a channel where logs should be sent (For privacy reasons, this should be a private channel).

Configuration
1. Update the `api.json` file with your bot's token, channel IDs, and other necessary configurations as per the instructions below.
2. Replace placeholders in the code with actual usernames and passwords as needed. Ensure to follow the format specified in the comments.
3. The bot's behavior and settings are configurable through the `api.json` file located in the project directory. Here's what you need to know:
   - **Token**: Your bot's token obtained from the Discord Developer Portal.
   - **Channel IDs**: Two channel IDs are required:
      - `channel_id_(for_pcaps)`: The ID of the channel where pcap files should be sent.
      - `channel_id_(for_logs)`: The ID of the channel where logs should be sent.
   - **Webhooks Username**: A list of usernames that the bot should respond to. Include `#0000` for webhook usernames.
   - **Log Using Debug**: A boolean value indicating whether to log using debug level, for production purposes set this to `false`.


Running the Bot
1. Ensure you have Python installed on their system.
2. Install required Python packages from the `requirements.txt` file using pip.

## 🚦 Usage

Ensure the bot is running in a Windows environment with admin privileges.
Attacker can interact with the bot by sending messages (try `/c2` first) in the configured channels
as well as reacting to the bots messages,
triggering responses based on message content and settings.

### 🤖 Discord Bot Side Troubleshooting
If you encounter any issues, check the following:
- Ensure your `api.json` file is correctly formatted and contains valid channel IDs.
- Verify that the bot is properly configured.
- Check the bot logs for any error messages.
- Ensure the bot is running in a Windows environment with admin privileges.
- Make sure the bot has proper admin permissions in the server.

### 💬 Common Issues
Here are some common issues and solutions to help you get back on track:-

#### ⏱️ Discord Log Upload Fails
- Check your internet connection to ensure it's stable (Maybe it's also the victim side).
- Ensure the Discord channel associated with the webhook allows file uploads (The log).
- Check if the log file grows too large, consider reducing the `max_size` parameter or implementing a log rotation mechanism.

## 📈 Contributing

Contributions are encouraged! Fork the repository, make changes, and submit pull requests.
Contributions to improve functionality, security, and usability are welcomed.

We would appreciate any contributions to additional c2 features.

## 📢 Support and Community

Join the Discord communities for support, discussions, and feature requests. 
Active forums and Discord channels offer assistance.

## 🌟 Giving Back

Consider contributing to the project, sharing experiences, or supporting the developers through donations.

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 📚 Additional Resources

- Discord Developer Portal: [https://discord.com/developers/docs](https://discord.com/developers/docs)

## 📧 Contact

For inquiries, feedback, or contributions,
please contact Shahm Najeeb using my [email](mailto:Nirt_12023@outlook.com)
