"""Rotating quote (every 15 min): shown when there are no major US releases. Funny, and only well-sourced attributions."""
from datetime import datetime

QUOTES = [
    ("I love deadlines. I love the whooshing noise they make as they go by.", "Douglas Adams"),
    ("Don't gamble; take all your savings and buy some good stock and hold it till it goes up, then sell it. "
     "If it don't go up, don't buy it.", "Will Rogers"),
    ("Weather forecast for tonight: dark.", "George Carlin"),
    ("I can resist everything except temptation.", "Oscar Wilde"),
    ("There are only two hard things in Computer Science: cache invalidation and naming things.", "Phil Karlton"),
    ("Time is an illusion. Lunchtime doubly so.", "Douglas Adams"),
    ("My fake plants died because I did not pretend to water them.", "Mitch Hedberg"),
    ("Rule No. 1: Never lose money. Rule No. 2: Never forget rule No. 1.", "Warren Buffett"),
    ("I intend to live forever. So far, so good.", "Steven Wright"),
    ("Get your facts first, and then you can distort them as you please.", "Mark Twain"),
    ("I'm not superstitious, but I am a little stitious.", "Michael Scott, The Office"),
    ("Housework can't kill you, but why take a chance?", "Phyllis Diller"),
    ("A day without sunshine is like, you know, night.", "Steve Martin"),
    ("Everything is funny, as long as it's happening to somebody else.", "Will Rogers"),
    ("The trouble with having an open mind, of course, is that people will insist on coming along "
     "and trying to put things in it.", "Terry Pratchett"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
]


ROTATE_MINUTES = 15


def quote_for(now: datetime) -> tuple[str, str]:
    """A different quote every ROTATE_MINUTES, cycling through the whole list."""
    slot = (now.toordinal() * 24 * 60 + now.hour * 60 + now.minute) // ROTATE_MINUTES
    return QUOTES[slot % len(QUOTES)]
