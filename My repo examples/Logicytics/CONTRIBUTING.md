# Contributing to Logicytics

Looking to contribute something to Logicytics? **Here's how you can help.**

Please take a moment to review this document to make the contribution
process easy and effective for everyone involved.

Following these guidelines helps to communicate that you respect the time of
the developers managing and developing this open source project. In return,
they should reciprocate that respect in addressing your issue or assessing
patches and features.

## Using the issue tracker

The [issue tracker](https://github.com/DefinetlyNotAI/Logicytics/issues) is
the preferred channel for bug reports and features requests
and submitting pull requests, but please respect the following
restrictions:

- Please **Do not** derail or troll issues. Keep the discussion on topic and
  respect the opinions of others.

- Please **Do not** post comments consisting solely of "+1" or "👍 ".
  Use [GitHub's "reactions" feature](https://blog.github.com/2016-03-10-add-reactions-to-pull-requests-issues-and-comments)
  instead. We reserve the right to delete comments which violate this rule.

## Issues assignment

I will be looking at the open issues, analyze them, and provide guidance on how to proceed.
Issues can be assigned to anyone other than me** and contributors are welcome
to participate in the discussion and provide their input on how to best solve the issue,
and even submit a PR if they want to.
Please wait that the issue is ready to be worked on before submitting a PR.
We don't want to waste your time.

Please keep in mind that I am small and have limited resources and am not always able to respond immediately.
I will try to provide feedback as soon as possible, but please be patient.
If you don't get a response immediately,
it doesn't mean that we are ignoring you or that we don't care about your issue or PR.
We will get back to you as soon as we can.

If you decide to pull a PR or fork the project, keep in mind that you should only add/edit the scripts you need to,
leave the Explain.md file and the updating of the structure file to me.

## Guidelines for Modifications 📃

When making modifications to the Logicytics project,
please adhere to the following guidelines to ensure consistency and maintainability:

- Use a consistent indentation.
- Add yourself to the [credits](CREDITS.md).
- Make sure you have done all the necessary steps in the [wiki](https://github.com/DefinetlyNotAI/Logicytics/wiki)
- Make sure you have tested your code.
  - Keep all tests in the test directory
- Make sure you have followed the instructions in the `--dev` flag.
- Make sure the coding style is similar to previous code
- Code is only written in `python, ps1 or batch` or is an `EXE` file (Highly Unadvised).
- You have not modified or changed the wrapper [`Logicytics.py`](CODE/Logicytics.py)
- All your code follows a strict logging system
  - If python, imports the [logger](CODE/__lib_log.py) class and uses it, with adhering to the critical code policy in the [wiki](https://github.com/DefinetlyNotAI/Logicytics/wiki)
    - For critical code you adhere to the `FILECODE-ERRORCODE-FUNCTIONCODE` formatting
  - If non-python, each print statement starts with either `INFO:` `WARNING:` or `ERROR:` to allow the wrapper to inject the [logger](CODE/__lib_log.py) class.
- Naming the code should follow these conventions:
  - File is either a `.py`, `.exe`, `.ps1`, `.bat` file
  - If it's a file to be run, shouldn't start with `_`
  - If it's a extra file/extra library, to make sure it isn't run, should start with `_`
- No code is allowed to have `if __name__ == '__main__'` or a similar functioning code

## Issues and labels 🛠️

Our bug tracker utilizes several labels to help organize and identify issues.

For a complete look at our labels, see the [project labels page](https://github.com/DefinetlyNotAI/Logicytics/labels).

## Bug reports 🐛

A bug is a _demonstrable problem_ that is caused by the code in the repository.
Good bug reports are extremely helpful!

Guidelines for bug reports:

1. **Use the GitHub issue search** &mdash; check if the issue has already been
   reported.

2. **Check if the issue has been fixed** &mdash; try to reproduce it using the
   latest `main` (or `version` branch if the issue is about a version) in the repository.

A good bug report shouldn't leave others needing to chase you up for more
information. Please try to be as detailed as possible in your report. What is
your environment? What steps will reproduce the issue? What browser(s) and OS
experience the problem? Do other browsers show the bug differently? What
would you expect to be the outcome? All these details will help people to fix
any potential bugs.

## Feature requests 🚀

Feature requests are welcome. But take a moment to find out whether your idea
fits with the scope and aims of the project. It's up to _you_ to make a strong
case to convince the project's developers of the merits of this feature. Please
provide as much detail and context as possible.

## Coding Standards 👨‍💻

- **Code Style**: Follow the project's existing code style.
- **Commit Messages**: Write clear and descriptive commit messages. Use the imperative mood (e.g., "Add feature" instead
  of "Added feature").
- **Documentation**: Update documentation as necessary to reflect any changes you make.

## Pull requests 📝

Good pull requests—patches, improvements, new features—are a fantastic
help. They should remain focused in scope and avoid containing unrelated
commits.

**Please ask first** before embarking on any **significant** pull request (e.g.
implementing features, refactoring code, porting to a different language),
otherwise you risk spending a lot of time working on something that the
project's developers might not want to merge into the project. For trivial
things, or things that don't require a lot of your time, you can go ahead and
make a PR.

Please adhere to the coding guidelines used throughout the
project (indentation, accurate comments, etc.) and any other requirements
(such as test coverage).

View the WiKi for more information on how to write pull requests.

**IMPORTANT**: By submitting a patch, you agree to allow the project owners to
license your work under the terms of the [MIT License](https://github.com/DefinetlyNotAI/Logicytics/blob/main/LICENSE) (
if it
includes code changes) and under the terms of the
[Creative Commons Attribution 3.0 Unported License](https://creativecommons.org/licenses/by/3.0/).

## License 📝

By contributing your code, you agree to license your contribution under
the [MIT License](https://github.com/DefinetlyNotAI/Logicytics/blob/main/LICENSE).
By contributing to the documentation, you agree to license your contribution under
the [Creative Commons Attribution 3.0 Unported License](https://creativecommons.org/licenses/by/3.0/).

## Communication 🗣️

- **Issues**: Use GitHub issues for bug reports and feature requests. Keep the discussion focused and relevant.
- **Pull Requests**: Use pull requests to propose changes. Be prepared to discuss your changes and address any feedback.

If you have any questions or need further clarification, please feel free to contact [us](mailto:Nirt_12023@outlook.com)

Thank you for your contributions!