"""
TINA Tools — Auto-registration
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from search import DEFINITIONS as SEARCH_DEFS, handle as search_handle
from weather import DEFINITIONS as WEATHER_DEFS, handle as weather_handle
from wikipedia import DEFINITIONS as WIKI_DEFS, handle as wiki_handle
from news import DEFINITIONS as NEWS_DEFS, handle as news_handle
from calendar_tool import DEFINITIONS as CAL_DEFS, handle as cal_handle

ALL_DEFINITIONS = SEARCH_DEFS + WEATHER_DEFS + WIKI_DEFS + NEWS_DEFS + CAL_DEFS

_HANDLERS = {}
for defn in SEARCH_DEFS:  _HANDLERS[defn["name"]] = search_handle
for defn in WEATHER_DEFS: _HANDLERS[defn["name"]] = weather_handle
for defn in WIKI_DEFS:    _HANDLERS[defn["name"]] = wiki_handle
for defn in NEWS_DEFS:    _HANDLERS[defn["name"]] = news_handle
for defn in CAL_DEFS:     _HANDLERS[defn["name"]] = cal_handle

def handle(name: str, inputs: dict) -> str:
    handler = _HANDLERS.get(name)
    if handler:
        return handler(name, inputs)
    return f"Unknown tool: {name}"