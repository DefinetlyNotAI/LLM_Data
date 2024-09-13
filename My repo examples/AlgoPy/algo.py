"""
------------------------------------------------------------------------------------------------------------------------

N = number of elements to process.
M = difference between the largest number and smallest number in the list.
K = integers length of the largest number in the list.
H = height of the tree.

### Time Complexity
- **O(1)**:
  - [Log.info]
  - [Log.warning]
  - [Log.error]
  - [Log.critical]
  - [Convert.memory]

- **O(n)**:
  - [Find.value_index]
  - [Validate.email]
  - [Validate.url]
  - [Validate.phone_number]
  - [Validate.CreditCard()]
  - [Convert.dec_to_roman]
  - [Convert.roman_to_dec]
  - [Find.total_vowels]
  - [Find.every_vowel]
  - [Convert.bin_to_dec]
  - [Convert.bin_to_hex]
  - [Convert.hex_to_bin]
  - [Convert.hex_to_dec]
  - [Sort.LinkedList().append]
  - [Sort.LinkedList().return_elements]
  - [Sort.TreeNode().sort]

- **O(n + m)**:
  - [Sort.using_counting_sort]

- **O(log n)**:
  - [Convert.dec_to_hex]
  - [Convert.dec_to_bin]

- **O(n log n)**:
  - [Find.largest]
  - [Find.smallest]
  - [Sort.using_quicksort]
  - [Sort.using_merge_sort]
  - [Sort.using_heap_sort]

- **O(n * k)**:
  - [Convert.dec_to_ascii]
  - [Sort.using_radix_sort]

- **O(n^2)**:
  - [Sort.using_selection]
  - [Sort.using_bubble]
  - [Sort.using_insertion]
  - [Sort.LinkedList().using_bubble]

- **O((n+1)! / 2) OR Unbounded(infinite)**:
  - [Sort.using_bogo_sort]

------------------------------------------------------------------------------------------------------------------------

### Space Complexity
- O(1):
  - [Find.value_index]
  - [Find.total_vowels]
  - [Find.every_vowel]
  - [Sort.using_selection]
  - [Sort.using_bubble]
  - [Sort.using_insertion]
  - [Sort.using_heap_sort]
  - [Convert.dec_to_ascii]
  - [Convert.dec_to_roman]
  - [Convert.roman_to_dec]
  - [Convert.bin_to_dec]
  - [Convert.bin_to_hex]
  - [Convert.hex_to_bin]
  - [Convert.hex_to_dec]
  - [Convert.dec_to_hex]
  - [Convert.dec_to_bin]
  - [Convert.memory]
  - [Sort.using_bogo_sort]
  - [Validate.email]
  - [Validate.url]
  - [Validate.phone_number]
  - [Validate.CreditCard()]
  - [Sort.LinkedList().using_bubble]
  - [Sort.LinkedList().append]

- O(n):
  - [Find.largest]
  - [Find.smallest]
  - [Log.info]
  - [Log.warning]
  - [Log.error]
  - [Log.critical]
  - [Sort.using_merge_sort]
  - [Sort.LinkedList().return_elements]

- O(h):
  - [Sort.TreeNode().sort]

- **O(n + k)**:
  - [Sort.using_radix_sort]

- **O(n + m)**:
  - [Sort.using_counting_sort]

- O(log n):
  - [Sort.using_quicksort]

------------------------------------------------------------------------------------------------------------------------
"""

# Fun Fact: Interstellar + Undertale + Deltarune + Stardew + Terraria + Minecraft = Life

import heapq
import os
import random
import re
import colorlog
from datetime import datetime


class Log:
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
        time = f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
        return time

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


class Find:
    def __init__(self):
        """
        Initializes a new instance of the Find class.

        The Find class provides methods for finding words in a text string.
        Or getting a values index in an array.
        Or getting the largest and smallest value in an array.


        Returns:
            None
        """
        self.special_y_words = [
            "Cry",
            "Dry",
            "Gym",
            "Hymn",
            "Lynx",
            "Myth",
            "Pry",
            "Rhythm",
            "Shy",
            "Spy",
            "Spry",
            "Sync",
            "Try",
            "Why",
            "City",
            "Party",
            "Fly",
            "Shy",
            "Wary",
            "Worthwhile",
            "Type",
            "Typical",
            "Thyme",
            "Cyst",
            "Symbol",
            "System",
            "Lady",
            "Pretty",
            "Very",
            "Deny",
            "Daddy",
            "Quickly",
        ]

    @staticmethod
    def __sort(List: list) -> list[int | float]:
        """
        Sorts a list of mixed data types, filtering out non-numeric values and returning a sorted list of integers and floats.

        Args:
            List (list): A list containing mixed data types.

        Returns:
            list[int | float]: A sorted list of integers and floats.

        Raises:
            Exception: If the input list is None.
        """
        if List is None:
            raise Exception("No input given.")

        converted_list = sorted(
            float(item) for item in List if isinstance(item, (int, float))
        )
        final_list = [
            int(item) if item.is_integer() else item for item in converted_list
        ]
        return final_list

    def __vowel_y(self, string: str, only_lowercase=False) -> str:
        """
        Determines the vowels to consider based on the presence of special words containing "y".

        Args:
            string (str): The input string to check for special words.
            only_lowercase (bool, optional): Whether to consider only lowercase vowels. Defaults to False.

        Returns:
            str: A string of vowels to consider, including "y" if a special word is found.

        Raises:
            Exception: If the input string is None.
        """
        if string is None:
            raise Exception("No input given.")
        if self.__value_index(self.special_y_words, string):
            if only_lowercase:
                vowels = "aeiouy"
            else:
                vowels = "aeiouyAEIOUY"
        else:
            if only_lowercase:
                vowels = "aeiou"
            else:
                vowels = "aeiouAEIOU"
        return vowels

    @staticmethod
    def __count_character(Word: str, Vowel: str) -> str:
        """
        Counts the occurrences of a specified vowel in a word.

        Args:
            Word (str): The input word to count the vowel in.
            Vowel (str): The vowel to count.

        Returns:
            str: A string containing the vowel and its count in the word.
        """
        count = 0
        for i in range(len(Word)):
            if Word[i] == Vowel:
                count += 1

        return f"{Vowel} {count}"

    @staticmethod
    def __value_index(array: list, Word: str) -> bool:
        """
        Checks if a given word exists in a specified array.

        Args:
            array (list): The list of values to search in.
            Word (str): The word to search for.

        Returns:
            bool: True if the word is found, False otherwise.
        """
        for index, value in enumerate(array):
            if value == Word:
                return True
        return False

    def largest_in_array(self, List: list[int | float]) -> int | float:
        """
        Finds the largest value in a given list of integers or floats.

        Args:
            List (list[int | float]): A list of integers or floats to find the largest value in.

        Returns:
            int | float: The largest value in the list, or None if the list is empty.

        Raises:
            Exception: If the input list is None.
        """
        if List is None:
            raise Exception("No input given.")
        largeList = self.__sort(List)
        if largeList is None:
            raise Exception("No input given.")
        return largeList[-1] if largeList else None

    def smallest_in_array(self, List: list[int | float]) -> int | float:
        """
        Finds the smallest value in a given list of integers or floats.

        Args:
            List (list[int | float]): A list of integers or floats to find the smallest value in.

        Returns:
            int | float: The smallest value in the list, or None if the list is empty.

        Raises:
            Exception: If the input list is None.
        """
        if List is None:
            raise Exception("No input given.")
        smallList = self.__sort(List)
        if smallList is None:
            raise Exception("No input given.")
        return smallList[0] if smallList else None

    def total_vowels_in_string(self, Word: str) -> int:
        """
        Counts the total number of vowels in a given string.

        Args:
            Word (str): The input string to count the vowels in.

        Returns:
            int: The total number of vowels in the string.

        Raises:
            Exception: If the input string is None.
        """
        if Word is None:
            raise Exception("No input given.")
        vowels = self.__vowel_y(Word)
        vowel_count = sum(1 for char in Word if char in vowels)
        return vowel_count

    def every_vowel_in_string(self, Word: str) -> str:
        """
        Checks if every vowel appears in a given string and returns the count of each vowel.

        Args:
            Word (str): The input string to check for vowels.

        Returns:
            str: A string containing the count of each vowel in the input string, separated by newline characters.

        Raises:
            Exception: If the input string is None.
        """
        if Word is None:
            raise Exception("No input given.")
        result = ""
        vowels = self.__vowel_y(Word, True)
        for vowel in vowels:
            result += self.__count_character(Word, vowel) + "\n"
        return result.rstrip("\n")

    @staticmethod
    def value_index_in_array(List: list, value_to_find: any) -> int | bool:
        """
        Finds the index of a specified value in a given list.

        Args:
            List (list): The list to search for the value in.
            value_to_find (any): The value to search for in the list.

        Returns:
            int | bool: The index of the value in the list if found, False otherwise.

        Raises:
            Exception: If either the list or the value to find is None.
        """
        if List is None or value_to_find is None:
            raise Exception("No input given.")
        for index, value in enumerate(List):
            if value == value_to_find:
                return index
        return False


class Sort:
    def __init__(self):
        """
        Initializes an instance of the class.

        The Sort class provides implementations of various sorting algorithms,
        including quick sort, merge sort, selection sort, bubble sort, insertion sort,
        heap sort, radix sort, counting sort, bogo sort, and linked list sorts.
        Each method sorts an array of integers or floats.

        It also includes sorting for linked lists and binary trees.
        With a way to also create them.

        The most powerful class in AlgoPy.

        """
        pass

    @staticmethod
    def __is_sorted(Array: list[int | float]) -> bool:
        """
        Checks if the elements in a given array are sorted in ascending order.

        Args:
            Array (list[int | float]): A list containing integers and/or floats.

        Returns:
            bool: True if the array is sorted, False otherwise.
        """
        return all(Array[i] <= Array[i + 1] for i in range(len(Array) - 1))

    @staticmethod
    def __merge(left: list[int | float], right: list[int | float]) -> list[int | float]:
        """
        Merges two sorted lists into a single sorted list.

        This function takes two lists of integers or floats as input,
        merges them into a single list, and returns the merged list.
        The merged list is sorted in ascending order.

        Args:
            left (list[int | float]): The first sorted list to merge.
            right (list[int | float]): The second sorted list to merge.

        Returns:
            list[int | float]: The merged sorted list.
        """
        result = []
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] < right[j]:
                result.append(left[i])
                i += 1
            else:
                result.append(right[j])
                j += 1
        result.extend(left[i:])
        result.extend(right[j:])
        return result

    def using_quick_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the quicksort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        if len(Array) <= 1:
            return Array
        pivot = Array[len(Array) // 2]
        left = [x for x in Array if x < pivot]
        middle = [x for x in Array if x == pivot]
        right = [x for x in Array if x > pivot]
        return self.using_quick_sort(left) + middle + self.using_quick_sort(right)

    def using_merge_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the merge sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        if len(Array) <= 1:
            return Array
        mid = len(Array) // 2
        left = Array[:mid]
        right = Array[mid:]
        return Sort.__merge(self.using_merge_sort(left), self.using_merge_sort(right))

    def using_selection_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the selection sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        for i in range(len(Array)):
            min_index = i
            for j in range(i + 1, len(Array)):
                if Array[min_index] > Array[j]:
                    min_index = j
            Array[i], Array[min_index] = Array[min_index], Array[i]
        return Array

    def using_bubble_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the bubble sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        n = len(Array)
        for i in range(n):
            for j in range(0, n - i - 1):
                if Array[j] > Array[j + 1]:
                    Array[j], Array[j + 1] = Array[j + 1], Array[j]
        return Array

    def using_insertion_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the insertion sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        for i in range(1, len(Array)):
            key = Array[i]
            j = i - 1
            while j >= 0 and key < Array[j]:
                Array[j + 1] = Array[j]
                j -= 1
            Array[j + 1] = key
        return Array

    def using_heap_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the heap sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        heapq.heapify(Array)
        return [heapq.heappop(Array) for _ in range(len(Array))]

    def using_radix_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the radix sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        if self.__is_sorted(Array):
            return Array

        max_value = max(Array)
        max_exponent = len(str(max_value))
        for exponent in range(max_exponent):
            digits = [[] for _ in range(10)]
            for num in Array:
                digit = (num // 10**exponent) % 10
                digits[digit].append(num)
            Array = []
            for digit_list in digits:
                Array.extend(digit_list)
        return Array

    def using_counting_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the counting sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")
        if self.__is_sorted(Array):
            return Array
        max_value = max(Array)
        min_value = min(Array)
        range_of_elements = max_value - min_value + 1
        count = [0] * range_of_elements
        output = [0] * len(Array)
        for num in Array:
            count[num - min_value] += 1
        for i in range(1, len(count)):
            count[i] += count[i - 1]
        for num in reversed(Array):
            output[count[num - min_value] - 1] = num
            count[num - min_value] -= 1
        return output

    def using_bogo_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the bogo sort algorithm.

        Don't actually use this - It's a joke

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None or contains non-integer values.
        """
        if Array is None:
            raise Exception("No input given.")

        while not self.__is_sorted(Array):
            random.shuffle(Array)

        return Array

    def using_stalin_sort(self, Array: list[int | float]) -> list[int | float]:
        """
        Sorts an array of integers or floats using the Stalin sort algorithm.

        Args:
            Array (list[int | float]): The input array to be sorted.

        Returns:
            list[int | float]: The sorted array.

        Raises:
            Exception: If the input array is None.
        """
        # Base case: If the list is empty or has only one element, it's already sorted.
        if Array is None:
            raise Exception("No input given. No input can be eliminated.")

        # Find the minimum element in the list
        min_value = min(Array)

        # Remove all occurrences of the minimum value from the list
        Array = [x for x in Array if x != min_value]

        # Recursively sort the rest of the list
        return [min_value] + self.using_stalin_sort(Array)

    @classmethod
    class LinkedList:
        def __init__(self, Data=None):
            """
            Initializes a new instance of the LinkedList class.

            Creates a new linked list node with the given data.

            Usage:
                linked_list = Sort.LinkedList()
                linked_list.append(5)
                linked_list.append(15)
                linked_list.append(3)
                linked_list.append(12)
                linked_list.append(9)
                linked_list.using_bubble()

            This method will sort the linked list in ascending order, based on the data stored in the nodes,
            of the linked list.

            Args:
                Data (any, optional): The data to be stored in the linked list node. Defaults to None.

            Returns:
                None
            """
            self.head = None
            self.data = Data
            self.next = None

        def __merge(self, start, mid, end):
            """
            Recursively merges two sorted linked lists into a single sorted linked list.

            Args:
                start (LinkedList): The starting node of the first linked list.
                mid (LinkedList): The ending node of the first linked list.
                end (LinkedList): The ending node of the second linked list.

            Returns:
                LinkedList: The merged and sorted linked list.
            """
            if start is None:
                return end
            if end is None:
                return start

            if start.data <= end.data:
                start.next = self.__merge(start.next, mid, end)
            else:
                end.next = self.__merge(start, mid, end)
                start, end = end, start

            return start

        def append(self, data: int | float) -> None:
            """
            Adds a new node to the end of the linked list.

            Args:
                data (int | float): The data to be stored in the new node.

            Returns:
                None
            """
            if not self.head:
                self.head = Sort().LinkedList(data)
            else:
                current = self.head
                while current.next:
                    current = current.next
                current.next = Sort().LinkedList(data)

        def return_elements(self) -> list[int | float]:
            """
            Returns a list of elements in the linked list.

            Returns:
                list[int | float]: A list of elements in the linked list.
            """
            elements = []
            current_node = self.head
            while current_node:
                elements.append(current_node.data)
                current_node = current_node.next
            return elements

        def using_bubble(self) -> None:
            """
            Sorts a linked list in ascending order using the bubble sort algorithm.

            This function iterates through the linked list, repeatedly swapping adjacent nodes if they are in the wrong order.
            The process is repeated until no more swaps are needed, indicating that the list is sorted.

            Returns:
                None
            """
            if self.head is None:
                return

            swapped = True
            while swapped:
                swapped = False
                current = self.head
                while current.next is not None:
                    if current.data > current.next.data:
                        current.data, current.next.data = (
                            current.next.data,
                            current.data,
                        )
                        swapped = True
                    current = current.next

    @classmethod
    class BinaryTree:
        def __init__(self, val=0, left=None, right=None):
            """
            Initializes a new instance of the BinaryTree class.

            Usage:
                # Define nodes for the binary tree
                sort_node = Sort.BinaryTree
                root = sort_node(5)  # root is the beginning of the binary tree
                root.left = sort_node(3)
                root.right = sort_node(7)
                root.left.left = sort_node(2)
                root.left.right = sort_node(4)
                root.right.left = sort_node(6)
                root.right.right = sort_node(8)

                # Now, let's sort the values in the binary tree using the sort method
                sorted_values = root.sort(root)  # root is the beginning of the binary tree, you can change this to any branch like root.left to only sort and show the values in the left branch
                print(sorted_values)

            This method will sort the binary tree in ascending order properly

            Args:
                val (int | float, optional): The value of the node. Defaults to 0.
                left (Sort.BinaryTree, optional): The left child node. Defaults to None.
                right (Sort.BinaryTree, optional): The right child node. Defaults to None.

            Returns:
                None
            """
            self.val = val
            self.left = left
            self.right = right

        def sort(self, root) -> list[int | float]:
            """
            Sorts a binary tree in-order and returns a list of the sorted values.

            Args:
                root (Sort.BinaryTree): The root node of the binary tree.

            Returns:
                list[int | float]: A list of the sorted values in the binary tree.
            """
            if root is None:
                return []

            left_values = self.sort(root.left)
            values = [root.val]
            right_values = self.sort(root.right)

            return left_values + values + right_values


class Validate:
    def __init__(self):
        """
        Initializes a new instance of the Validate class.

        This class provides methods for validating URLs,
        email addresses, and phone numbers as well as credit card by specifics.

        Returns:
            None
        """
        self.url = r"^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w\.-]*)*\/?$"
        self.email = r"^[a-zA-Z0-9!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        self.phone = r"^\+?[0-9]{1,3}?[ -]?[0-9]{1,3}?[ -]?[0-9]{1,4}$"

    def this_email(self, email_address: str) -> bool:
        """
        Validates an email address against a set of predefined rules.

        Args:
            email_address (str): The email address to be validated.

        Returns:
            bool: True if the email address is valid, False otherwise.
        """
        if len(email_address) < 1 or len(email_address) > 320:
            return False
        if " " in email_address:
            return False
        pattern = re.compile(self.email)
        return bool(pattern.search(email_address))

    def this_url(self, url_string: str) -> bool:
        """
        Validates a URL against a set of predefined rules.

        Args:
            url_string (str): The URL to be validated.

        Returns:
            bool: True if the URL is valid, False otherwise.
        """
        if " " in url_string:
            return False
        pattern = re.compile(self.url)
        return bool(pattern.search(url_string))

    def this_phone_number(self, phone_number: int | str) -> bool:
        """
        Validates a phone number against a set of predefined rules.

        Args:
            phone_number (int | str): The phone number to be validated.

        Returns:
            bool: True if the phone number is valid, False otherwise.
        """
        pattern = re.compile(self.phone)
        return bool(pattern.match(str(phone_number)))

    class CreditCard:
        def __init__(self):
            """
            Validates a card number using the Luhn algorithm.
            Specify in specifics inside the class.

            Returns a boolean value if the card number is valid or not.
            """
            pass

        @staticmethod
        def __luhn_algorithm(card_number: int) -> bool:
            """
            Validates a card number using the Luhn algorithm.

            Args:
                card_number (int): The card number to validate.

            Returns:
                bool: True if the card number is valid, False otherwise.
            """
            num_list = [int(digit) for digit in str(card_number)]
            num_list.reverse()
            total = 0
            for i, num in enumerate(num_list):
                doubled = num * 2
                if doubled > 9:
                    doubled -= 9
                total += doubled
            return total % 10 == 0

        @classmethod
        def american_express(cls, card_number: int) -> bool:
            """
            Validates American Express card numbers.
            """
            return cls.__luhn_algorithm(card_number) and (
                    str(card_number).startswith(("34", "37"))
                    and 15 <= len(str(card_number)) <= 16
            )

        @classmethod
        def china_unionpay(cls, card_number: int) -> bool:
            """
            Validates China UnionPay card numbers.
            """
            return cls.__luhn_algorithm(card_number) and (
                    str(card_number).startswith(
                        (
                            "62",
                            "64",
                            "65",
                            "66",
                            "67",
                            "68",
                            "69",
                            "92",
                            "93",
                            "94",
                            "95",
                            "96",
                            "97",
                            "98",
                            "99",
                        )
                    )
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def dankort(cls, card_number: int) -> bool:
            """
            Validates Dankort card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(card_number).startswith("49")
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def diners_club(cls, card_number: int) -> bool:
            """
            Validates Diners Club International card numbers.
            """
            return cls.__luhn_algorithm(card_number) and (
                    str(card_number).startswith(("36", "38"))
                    and 14 <= len(str(card_number)) <= 19
            )

        @classmethod
        def discover(cls, card_number: int) -> bool:
            """
            Validates Discover card numbers.
            """
            return cls.__luhn_algorithm(card_number) and (
                    str(card_number).startswith(
                        (
                            "6011",
                            "6221",
                            "6222",
                            "6223",
                            "623",
                            "624",
                            "625",
                            "626",
                            "627",
                            "628",
                            "641",
                            "642",
                            "643",
                            "644",
                            "645",
                            "646",
                            "647",
                            "648",
                            "649",
                            "65",
                            "66",
                            "67",
                            "68",
                            "69",
                            "71",
                            "72",
                            "73",
                            "74",
                            "75",
                            "76",
                            "77",
                            "78",
                            "79",
                        )
                    )
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def jcb(cls, card_number: int) -> bool:
            """
            Validates JCB card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(card_number).startswith("35")
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def maestro(cls, card_number: int) -> bool:
            """
            Validates Maestro card numbers.
            """
            return cls.__luhn_algorithm(card_number) and (
                    str(card_number).startswith(
                        (
                            "50",
                            "51",
                            "52",
                            "53",
                            "54",
                            "55",
                            "56",
                            "57",
                            "58",
                            "60",
                            "61",
                            "62",
                            "63",
                            "64",
                            "65",
                            "66",
                            "67",
                            "68",
                            "69",
                            "70",
                            "71",
                            "72",
                            "73",
                            "74",
                            "75",
                            "76",
                            "77",
                            "78",
                            "79",
                        )
                    )
                    and 12 <= len(str(card_number)) <= 19
            )

        @classmethod
        def mastercard(cls, card_number: int) -> bool:
            """
            Validates Mastercard card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(card_number).startswith(
                ("51", "52", "53", "54", "55", "56", "57", "58", "59")
            )
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def visa(cls, card_number: int) -> bool:
            """
            Validates Visa card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(card_number).startswith("4")
                    and 13 <= len(str(card_number)) <= 16
            )

        @classmethod
        def visa_electron(cls, card_number: int) -> bool:
            """
            Validates Visa Electron card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(card_number).startswith(
                ("40", "41", "42", "43", "44", "45", "46", "47", "48", "49")
            )
                    and 16 <= len(str(card_number))
            )

        @classmethod
        def v_pay(cls, card_number: int) -> bool:
            """
            Validates V Pay card numbers.
            """
            return (
                    cls.__luhn_algorithm(card_number)
                    and str(str(card_number)).startswith("28")
                    and 16 <= len(str(str(card_number)))
            )

        @classmethod
        def any(cls, card_number: int) -> bool:
            """
            Validates any card number just by passing it to the Luhn algorithm.
            """
            return cls.__luhn_algorithm(card_number)


class Convert:
    def __init__(self, show_warnings=False):
        """
        Initializes an instance of the Convert class.

        The Convert class provides methods to convert numbers from one base to another.
        As well as converting from decimal to ascii numeral art.
        Finally, it provides a method to convert from memory units (bytes, KB, MB, GB, etc.)

        Args:
            show_warnings (bool, optional): Whether to display warnings for certain operations.
                Defaults to False.
        """
        self.mapping = {
            10000: "/X/",
            9000: "M/X/",
            8000: "/VIII/",
            5000: "/V/",
            4000: "M/V/",
            1000: "M",
            900: "CM",
            500: "D",
            400: "CD",
            100: "C",
            90: "XC",
            50: "L",
            40: "XL",
            10: "X",
            9: "IX",
            5: "V",
            4: "IV",
            1: "I",
        }
        self.roman_to_numerical = {
            "I": 1,
            "V": 5,
            "X": 10,
            "L": 50,
            "C": 100,
            "D": 500,
            "M": 1000,
            "IV": 4,
            "IX": 9,
            "XL": 40,
            "XC": 90,
            "CD": 400,
            "CM": 900,
            "/X/": 10000,
            "M/X/": 9000,
            "/VIII/": 8000,
            "/V/": 5000,
            "M/V/": 4000,
        }
        self.memory_dict = {
            "Bit": 1,
            "Byte": 8,
            "KB": 8 * 1000,
            "MB": 8 * (1000**2),
            "GB": 8 * (1000**3),
            "TB": 8 * (1000**4),
            "PB": 8 * (1000**5),
            "KiB": 8 * 1024,
            "MiB": 8 * (1024**2),
            "GiB": 8 * (1024**3),
            "TiB": 8 * (1024**4),
            "PiB": 8 * (1024**5),
            "Kb": 1000,
            "Mb": 1000**2,
            "Gb": 1000**3,
            "Tb": 1000**4,
            "Pb": 1000**5,
            "Kib": 1024,
            "Mib": 1024**2,
            "Gib": 1024**3,
            "Tib": 1024**4,
            "Pib": 1024**5,
        }

        Zero = [
            "  ***  ",
            " *   * ",
            "*     *",
            "*     *",
            "*     *",
            " *   * ",
            "  ***  ",
        ]

        One = [" * ", "** ", " * ", " * ", " * ", " * ", "***"]

        Two = [" *** ", "*   *", "*  * ", "  *  ", " *   ", "*    ", "*****"]

        Three = [" *** ", "*   *", "    *", "  ** ", "    *", "*   *", " *** "]

        Four = ["   *  ", "  **  ", " * *  ", "*  *  ", "******", "   *  ", "   *  "]

        Five = ["*****", "*    ", "*    ", " *** ", "    *", "*   *", " *** "]

        Six = [" *** ", "*    ", "*    ", "**** ", "*   *", "*   *", " *** "]

        Seven = ["*****", "    *", "   * ", "  *  ", " *   ", "*    ", "*    "]

        Eight = [" *** ", "*   *", "*   *", " *** ", "*   *", "*   *", " *** "]

        Nine = [" ****", "*   *", "*   *", " ****", "    *", "    *", "    *"]

        self.digits = [Zero, One, Two, Three, Four, Five, Six, Seven, Eight, Nine]
        self.show_warnings = show_warnings

    @staticmethod
    def __check_input_type(value, expected_type) -> bool:
        if not isinstance(value, expected_type):
            raise Exception(
                f"Expected {expected_type.__name__}, got {type(value).__name__}"
            )
        return True

    def dec_to_roman(self, Number: int) -> str:
        """
        Converts a decimal number to a Roman numeral.

        Args:
            Number (int): The decimal number to convert.

        Returns:
            str: The Roman numeral representation of the input number.

        Raises:
            Exception: If the input number is None.
            Exception: If the input number is less than or equal to 1.

        Notes:
            - If the input number is greater than 10000 and the `show_warnings` flag is set,
              a warning message is printed.
        """
        if Number is None:
            raise Exception("No input given.")
        if Number <= 1:
            raise Exception("Input must be greater or equal to 1.")
        if Number > 10000 and self.show_warnings:
            print("Input is too large. This may result in inaccurate results.")

        result = ""
        for numerical, roman in sorted(self.mapping.items(), reverse=True):
            while Number >= numerical:
                result += roman
                Number -= numerical
        return result

    def roman_to_dec(self, Roman) -> int:
        """
        Converts a Roman numeral to a decimal number.

        Args:
            Roman (str): The Roman numeral to convert.

        Returns:
            int: The decimal representation of the input Roman numeral.

        Raises:
            Exception: If the input is not a string, not uppercase, or None.
        """
        if not isinstance(Roman, str):
            raise Exception("Input must be a string.")
        elif not Roman.isupper():
            raise Exception("Input must be uppercase.")
        elif Roman is None:
            raise Exception("Input cannot be None.")
        i = 0
        num = 0
        Roman = Roman.upper()
        while i < len(Roman):
            if i + 1 < len(Roman) and Roman[i: i + 2] in self.roman_to_numerical:
                num += self.roman_to_numerical[Roman[i: i + 2]]
                i += 2
            else:
                num += self.roman_to_numerical[Roman[i]]
                i += 1
        return num

    def dec_to_ascii(self, Number: int | str) -> str:
        """
        Converts a decimal number to its ASCII art representation.

        Args:
            Number (int | str): The decimal number to convert.

        Returns:
            str: The ASCII art representation of the input number.

        Raises:
            Exception: If the input number is None.
        """
        Number = str(Number)
        if Number is None:
            raise Exception("No input given.")
        ascii_art_lines = []
        for i in range(7):
            line = ""
            for j in range(len(Number)):
                current_num = int(Number[j])
                digit = self.digits[current_num]
                line += digit[i] + "  "
            ascii_art_lines.append(line)
        ascii_art = "\n".join(ascii_art_lines)
        return ascii_art

    def bin_to_hex(self, Binary_Number: int) -> str:
        """
        Converts a binary number to its hexadecimal representation.

        Args:
            Binary_Number (int): The binary number to convert.

        Returns:
            str: The hexadecimal representation of the input binary number.

        Raises:
            Exception: If the input binary number is None.
        """
        if Binary_Number is None:
            raise Exception("Conversion failed: No binary number provided")
        Binary_Number = str(Binary_Number)
        self.__check_input_type(Binary_Number, str)
        Hexadecimal_Number = hex(int(Binary_Number, 2))[2:]
        return Hexadecimal_Number.upper()

    def bin_to_dec(self, Binary_Number: int) -> int:
        """
        Converts a binary number to its decimal representation.

        Args:
            Binary_Number (int): The binary number to convert.

        Returns:
            int: The decimal representation of the input binary number.

        Raises:
            Exception: If the input binary number is None.
        """
        if Binary_Number is None:
            raise Exception("Conversion failed: No binary number provided")
        Binary_Number = str(Binary_Number)
        if not self.__check_input_type(Binary_Number, str):
            return False
        return int(Binary_Number, 2)

    def dec_to_hex(self, Decimal_Number: int) -> str:
        """
        Converts a decimal number to its hexadecimal representation.

        Args:
            Decimal_Number (int): The decimal number to convert.

        Returns:
            str: The hexadecimal representation of the input decimal number.

        Raises:
            Exception: If the input decimal number is None.
        """
        if Decimal_Number is None:
            raise Exception("Conversion failed: No decimal number provided")
        self.__check_input_type(Decimal_Number, (int, str))
        Hexadecimal_Number = hex(Decimal_Number)[2:]
        return Hexadecimal_Number.upper()

    def dec_to_bin(self, Decimal_Number: int) -> int:
        """
        Converts a decimal number to its binary representation.

        Args:
            Decimal_Number (int): The decimal number to convert.

        Returns:
            int: The binary representation of the input decimal number.

        Raises:
            Exception: If the input decimal number is None.
        """
        if Decimal_Number is None:
            raise Exception("Conversion failed: No decimal number provided")
        self.__check_input_type(Decimal_Number, (int, str))
        Binary_Number = bin(Decimal_Number)[2:]
        return int(Binary_Number)

    def hex_to_bin(self, Hexadecimal_Number: str) -> int:
        """
        Converts a hexadecimal number to its binary representation.

        Args:
            Hexadecimal_Number (str): The hexadecimal number to convert.

        Returns:
            int: The binary representation of the input hexadecimal number.

        Raises:
            Exception: If the input hexadecimal number is None.
        """
        if Hexadecimal_Number is None:
            raise Exception("Conversion failed: No hexadecimal number provided")
        self.__check_input_type(Hexadecimal_Number, str)
        Binary_Number = bin(int(Hexadecimal_Number, 16))[2:]
        return int(Binary_Number)

    def hex_to_dec(self, Hexadecimal_Number: str) -> int:
        """
        Converts a hexadecimal number to its decimal representation.

        Args:
            Hexadecimal_Number (str): The hexadecimal number to convert.

        Returns:
            int: The decimal representation of the input hexadecimal number.

        Raises:
            Exception: If the input hexadecimal number is None.
        """
        if Hexadecimal_Number is None:
            raise Exception("Conversion failed: No hexadecimal number provided")
        if not self.__check_input_type(Hexadecimal_Number, str):
            return False
        return int(Hexadecimal_Number, 16)

    def memory(self, number: int, input_unit: str, output_unit: str) -> str:
        """
        Converts a given number from one unit of memory to another.

        Args:
            number (int): The number to be converted.
            input_unit (str): The unit of the input number.
            output_unit (str): The unit to which the number should be converted.

        Returns:
            str: The converted number as a string, rounded to two decimal places, followed by the output unit.

        Raises:
            Exception: If the input number, input unit, or output unit is invalid.
        """
        if number is None or input_unit is None or output_unit is None:
            raise Exception(
                "Invalid input. Number, input_unit, and output_unit must all be provided."
            )
        if (
                not isinstance(number, int)
                or input_unit not in self.memory_dict
                or output_unit not in self.memory_dict
        ):
            raise Exception(
                f"Invalid input. Number must be an integer, and both units must be one of the following units: \n    {str(self.memory_dict.keys()).removeprefix('dict_keys([').removesuffix('])')}."
            )
        input_factor = self.memory_dict[input_unit]
        number_in_bits = number * input_factor
        output_factor = self.memory_dict[output_unit]
        final_number = number_in_bits / output_factor
        return f"{final_number:.2f} {output_unit}"
