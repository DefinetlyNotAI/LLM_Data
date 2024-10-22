import requests
from __lib_actions import *
from __lib_log import Log


class IP:
    @staticmethod
    def __get_my_ip():
        """
        Retrieves the user's current IP address from the ipify API.

        Returns:
            str: The user's current IP address.
        """
        try:
            response = requests.get("https://api.ipify.org")
            log.info("IP received successfully")
            return response.text
        except Exception as e:
            log.error(f"Failed to get IP: {e}")

    @staticmethod
    def __get_location_data(ip, api_key=None):
        """
        Retrieves location data for a given IP address.

        Args:
            ip (str): The IP address for which to retrieve location data.
            api_key (str, optional): The API key for the ipgeolocation API. Defaults to None.

        Returns:
            dict or None: A dictionary containing the location data if an API key is provided, otherwise None.
        """
        if api_key is None:
            log.warning("No API key provided. Location data will not be available.")
            return None
        base_url = f"https://api.ipgeolocation.io/ipgeo?apiKey={api_key}&ip={ip}"
        try:
            response = requests.get(base_url)
            log.info("Location data received successfully")
            return response.json()
        except Exception as e:
            log.error(f"Failed to get location data: {e}")

    def scraper(self):
        """
        Scrapes the user's current IP address and its corresponding location data.

        Writes the location data to a JSON file named 'location_data.json' in the current directory.

        Logs an info message when the IP scraper is executed successfully.

        Returns:
            None
        """
        open("location_data.json", "w").write(
            json.dumps(self.__get_location_data(self.__get_my_ip()), indent=4)
        )
        log.info("IP Scraper Executed")


log = Log(debug=DEBUG)
IP().scraper()
