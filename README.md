# Mercatores-AutoModerator
This a bot for the [xkcd forums](http://forums.xkcd.com) that runs the game of [Mercatores](http://forums.xkcd.com/viewtopic.php?f=14&t=108581&hilit=mercatores) on a forum thread

To use, clone into a new directory and run `python3 mercatores.py --setup`. It will prompt for a few pieces of information and setup the database. Then run it without any arguments to check the thread for new actions (you may want to schedule this to run regularly).

Note that this is still in development and contains a large number of bugs which may prevent it from working at all.

This requires Python 3, as well as the Python libraries [requests](https://pypi.python.org/pypi/requests), [dateutil](https://pypi.python.org/pypi/python-dateutil), and [Beautiful Soup 4](https://pypi.python.org/pypi/beautifulsoup4/4.3.2).
