"""Logging senza URL sensibili della Bot API, sia in polling sia su Render."""
import logging
import re


class RedactingFormatter(logging.Formatter):
    def __init__(self, token=None):
        super().__init__('%(asctime)s %(levelname)s %(name)s: %(message)s')
        self.token = token

    def format(self, record):
        # Dopo la formattazione: copre anche argomenti ed eventuali traceback.
        text = super().format(record)
        if self.token:
            text = text.replace(self.token, '[BOT_TOKEN]')
        return re.sub(r'\b(?:bot)?\d{5,}:[A-Za-z0-9_-]+', '[BOT_TOKEN]', text)


def configure_logging(token=None):
    logging.basicConfig(level=logging.INFO)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(token))
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
