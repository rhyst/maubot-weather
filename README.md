# WeatherBot

A simple [maubot](https://github.com/maubot/maubot) that scrapes windy.com for a multi-model forecast given a set of coordinates.

## Usage

Send the following messages to receive a reply from the bot:

- `<lat> <lon>` - Reply with the forecast for the given lat lon
- `version` - Reply with the bot version
- Share a location with the bot for the forecast for that location

Any other message will cause the bot to reply with help text.

## Requirements

A `maubot` docker image or other environment with `pyppeteer` installed. See [rhyst/maubot](https://github.com/rhyst/maubot-weather).
