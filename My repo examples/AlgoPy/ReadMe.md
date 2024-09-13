# AlgoPy


<div align="center">
    <a href="https://github.com/DefinetlyNotAI/AlgoPy/issues"><img src="https://img.shields.io/github/issues/DefinetlyNotAI/AlgoPy" alt="GitHub Issues"></a>
    <a href="https://github.com/DefinetlyNotAI/AlgoPy/tags"><img src="https://img.shields.io/github/v/tag/DefinetlyNotAI/AlgoPy" alt="GitHub Tag"></a>
    <a href="https://github.com/DefinetlyNotAI/AlgoPy/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/t/DefinetlyNotAI/AlgoPy" alt="GitHub Commit Activity"></a>
    <a href="https://github.com/DefinetlyNotAI/AlgoPy/languages"><img src="https://img.shields.io/github/languages/count/DefinetlyNotAI/AlgoPy" alt="GitHub Language Count"></a>
    <a href="https://github.com/DefinetlyNotAI/AlgoPy/actions"><img src="https://img.shields.io/github/check-runs/DefinetlyNotAI/AlgoPy/main" alt="GitHub Branch Check Runs"></a>
    <a href="https://github.com/DefinetlyNotAI/AlgoPy"><img src="https://img.shields.io/github/repo-size/DefinetlyNotAI/AlgoPy" alt="GitHub Repo Size"></a>
    <a href="https://codeclimate.com/github/DefinetlyNotAI/AlgoPy/maintainability"><img src="https://api.codeclimate.com/v1/badges/a7972706e1244b994e3a/maintainability" /></a>
</div>

---

## Overview

**AlgoPy** is a comprehensive collection of utilities
designed to streamline various tasks in software development.
It includes robust logging capabilities and efficient algorithms for sorting and searching data structures.
Whether you're building applications or maintaining systems,
**AlgoPy** offers tools to enhance productivity and reliability.

## Features

- Powerful logging system for tracking application events and errors.
- Efficient sorting and searching algorithms for quick data manipulation.
- Easy-to-use Library for rapid integration into projects.
- Super robust easy to implement.

## Getting Started

To get started with **AlgoPy**, follow these steps:

### Prerequisites

Ensure you have Python installed on your system. **AlgoPy** supports Python versions 3.6 and above.
You must have `pip` installed to install the required packages.

Requirements are:
- colorlog~=6.8.2
- DateTime~=5.5

To install: `pip install -r requirements.txt`

---

# Usage

## Log Class Documentation

### Overview
The `Log` class provides a flexible logging system that supports both console logging via `colorlog` and file logging. It is designed to be easily configurable through parameters such as log level, color scheme, and log file name. This class is particularly useful for applications requiring detailed logging for debugging and monitoring purposes.

### Features
- Supports both console and file logging.
- Configurable log levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- Customizable color schemes for console output.
- Automatic creation of log file if it does not exist.
- Timestamped entries for easy tracking of events.

### Usage Example
```python
from algopy import Log  # Assuming the class definition is saved in log_class_definition.py

# Initialize the Log class with custom settings
logger = Log(filename="custom_log.log", use_colorlog=True, DEBUG=True, debug_color="cyan", info_color="green")

# Example usage
logger.info("This is an informational message.")
logger.warning("This is a warning message.")
logger.error("This is an error message.")
logger.critical("This is a critical message.")
```

### Configuration Options
- `filename`: The name of the log file. Default is `"Server.log"`.
- `use_colorlog`: Whether to enable colored logging in the console. Default is `True`.
- `DEBUG`: Enable debug-level logging. Default is `False`.
- `debug_color`, `info_color`, `warning_color`, `error_color`, `critical_color`: Colors for different log levels in the console. Defaults are `"cyan"` for debug, `"green"` for info, `"yellow"` for warning, and `"red"` for error and critical.
- `colorlog_fmt_parameters`: Format of the log message. Default includes timestamp, log level, and message.

### Subclasses and Methods
The `Log` class does not have direct subclasses but can be extended for specialized logging needs.

## Find Class Documentation

### Overview
The `Find` class offers various methods for searching and analyzing lists and strings. It includes functionality for sorting, finding special words containing "y", counting vowels, and identifying the largest/smallest values in a list.

### Features
- Searches for special words containing "y" in a given string.
- Counts the total number of vowels in a string.
- Identifies whether every vowel appears in a string.
- Finds the largest and smallest values in a list after sorting.

### Usage Example
```python
from algopy import Find  # Assuming the class definition is saved in find_class_definition.py

finder = Find()

# Example usage
special_words = finder.special_y_words
print(special_words)

total_vowels = finder.total_vowels_in_string("Hello World")
print(total_vowels)

every_vowel = finder.every_vowel_in_string("Hello World")
print(every_vowel)
```

### Methods
- `__vowel_y(string: str, only_lowercase=False)`: Determines the vowels to consider based on the presence of special words containing "y".
- `__count_character(Word: str, Vowel: str)`: Counts occurrences of a specified vowel in a word.
- `largest_in_array(List: list[int | float])`: Finds the largest value in a list after sorting.
- `smallest_in_array(List: list[int | float])`: Finds the smallest value in a list after sorting.
- `total_vowels_in_string(Word: str)`: Counts the total number of vowels in a string.
- `every_vowel_in_string(Word: str)`: Checks if every vowel appears in a string.

## Sort Class Documentation

### Overview
The `Sort` class provides implementations of various sorting algorithms, including quick sort, merge sort, selection sort, bubble sort, insertion sort, heap sort, radix sort, counting sort, bogo sort, and linked list sorts. Each method sorts an array of integers or floats.

### Features
- Implements multiple sorting algorithms for educational and practical purposes.
- Includes sorting for linked lists and binary trees.

### Usage Example

You may also add `.reverse()` to the methods to reverse the order of the array after sorting them.

```python
from algopy import Sort  # Assuming the class definition is saved in sort_class_definition.py

sorter = Sort()

# Example usage for basic array sorting
numbers = [5, 3, 8, 4, 2]
sorted_numbers = sorter.using_quick_sort(numbers)
print(sorted_numbers)

# Example usage for linked array sorting
# Creating a LinkedList instance and populating it with some integers.
linked_list = Sort.LinkedList()
linked_list.append(5)
linked_list.append(15)
linked_list.append(3)
linked_list.append(12)
linked_list.append(9)
print("Before sorting:")
print(linked_list.return_elements())
# Using the bubble sort method to sort the linked list.
linked_list.using_bubble()
print("After sorting using bubble sort:")
print(linked_list.return_elements())

# Example usage for binary tree sorting
# Define nodes for the binary tree
sort_node = Sort.BinaryTree
root = sort_node(5)  # root is the beginning of the binary tree
root.left = sort_node(3)
root.right = sort_node(7)
root.left.left = sort_node(2)
root.left.right = sort_node(4)
root.right.left = sort_node(6)
root.right.right = sort_node(8)
# Let's print the values in the binary tree UNSORTED.
print(root.val, root.left.val, root.right.val, root.left.left.val, root.left.right.val, root.right.left.val,
      root.right.right.val)
# Now, let's sort the values in the binary tree using the sort method
sorted_values = root.sort(root)  # root is the beginning of the binary tree, you can change this to any branch like root.left to only sort and show the values in the left branch
print(sorted_values)
```

### Sorting Algorithms
- `using_quick_sort(Array: list[int | float])`: Quick sort implementation.
- `using_merge_sort(Array: list[int | float])`: Merge sort implementation.
- `using_selection_sort(Array: list[int | float])`: Selection sort implementation.
- `using_bubble_sort(Array: list[int | float])`: Bubble sort implementation.
- `using_insertion_sort(Array: list[int | float])`: Insertion sort implementation.
- `using_heap_sort(Array: list[int | float])`: Heap sort implementation.
- `using_radix_sort(Array: list[int | float])`: Radix sort implementation.
- `using_counting_sort(Array: list[int | float])`: Counting sort implementation.
- `using_bogo_sort(Array: list[int | float])`: Bogo sort implementation.
- `using_stalin_sort(Array: list[int | float])`: Stalin sort implementation.

### Linked List Sort
- `using_bubble()`: Sorts a linked list using bubble sort.

### Binary Tree Sort
- `sort(root)`: Sorts a binary tree in ascending order.

## Validate Class Documentation

### Overview
The `Validate` class provides methods for validating URLs, emails, and phone numbers according to regular expressions. It ensures that inputs conform to expected patterns, making it useful for form validation and data sanitization.

### Features
- Validates URLs against a standard regex pattern.
- Validates emails against a standard regex pattern.
- Validates phone numbers against a standard regex pattern.

### Usage Example

```python
from algopy import Validate  # Assuming the class definition is saved in validate_class_definition.py

validator = Validate()

# Example usage
email_valid = validator.this_email("example@example.com")
print(email_valid)

url_valid = validator.this_url("https://example.com")
print(url_valid)

phone_valid = validator.this_phone_number("+971501234567")
print(phone_valid)
```

### Validation Methods
- `this_email(email_address: str)`: Validates an email address.
- `this_url(url_string: str)`: Validates a URL.
- `this_phone_number(phone_number: int | str)`: Validates a phone number.

### Credit Card Validation
The `Validate` class also includes methods for validating credit card numbers using the Luhn algorithm and specific card type checks.

Based on the provided `Convert` class code, here's a comprehensive README entry in Markdown format:

## Convert Class Documentation

### Overview
The `Convert` class is designed to facilitate various conversions between different numeral systems, including decimal to Roman numerals, Roman numerals to decimals, ASCII art generation from numbers, and conversions between binary, decimal, and hexadecimal representations. Additionally, it supports memory unit conversion (e.g., bytes to kilobytes).

### Features
- Converts decimal numbers to Roman numerals.
- Converts Roman numerals to decimal numbers.
- Generates ASCII art from decimal numbers.
- Converts between binary, decimal, and hexadecimal representations.
- Converts memory units (bytes, KB, MB, GB, etc.) accurately.

### Usage Example
```python
from algopy import Convert  # Assuming the class definition is saved in convert_class_definition.py

converter = Convert(show_warnings=True)

# Example usage
roman_numeral = converter.dec_to_roman(42)
print(roman_numeral)

decimal_number = converter.roman_to_dec("XLII")
print(decimal_number)

ascii_art = converter.dec_to_ascii(12345)
print(ascii_art)

binary_number = converter.bin_to_dec(1010)
print(binary_number)

hexadecimal_number = converter.dec_to_hex(255)
print(hexadecimal_number)

memory_conversion = converter.memory(1024, 'KB', 'GB')
print(memory_conversion)
```

### Conversion Methods
- `dec_to_roman(Number: int)`: Converts a decimal number to its Roman numeral equivalent.
- `roman_to_dec(Roman: str)`: Converts a Roman numeral string to its decimal equivalent.
- `dec_to_ascii(Number: int | str)`: Generates ASCII art representation of a number.
- `bin_to_dec(Binary_Number: int)`: Converts a binary number to its decimal equivalent.
- `dec_to_hex(Decimal_Number: int)`: Converts a decimal number to its hexadecimal equivalent.
- `dec_to_bin(Decimal_Number: int)`: Converts a decimal number to its binary equivalent.
- `hex_to_bin(Hexadecimal_Number: str)`: Converts a hexadecimal number to its binary equivalent.
- `hex_to_dec(Hexadecimal_Number: str)`: Converts a hexadecimal number to its decimal equivalent.
- `memory(number: int, input_unit: str, output_unit: str)`: Converts a number between different memory units.

### Note
- The `show_warnings` parameter controls whether warnings are displayed for certain operations, such as converting very large numbers to Roman numerals.
- All methods perform input type checking to ensure correctness and raise exceptions for invalid inputs.

## Contributing

We welcome contributions from the community.
If you'd like to contribute, please fork the repository,
make your changes, and submit a pull request.

## License

**AlgoPy** is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
