# WeatherBot

A simple [maubot](https://github.com/maubot/maubot) that scrapes windy.com for a multi-model forecast given a set of coordinates. Docs are [here](https://docs.mau.fi/maubot/index.html).

## Installation

You will need `maubot` running on your matrix server. The instructions for running this manually are [here](https://docs.mau.fi/maubot/usage/setup/index.html) but you may be using something else to manage your matrix instance (like [matrix-docker-ansible-deploy](https://github.com/spantaleev/matrix-docker-ansible-deploy/)) in which case refer to that.

This bot requires `pyppeteer` to be installed. See [rhyst/maubot](https://github.com/rhyst/maubot-weather) for a modified `maubot` image that you can use if you are running via docker.

Once you have `maubot` running you can visit it's web management page to install `maubot-weather`. Follow the instructions [here](https://docs.mau.fi/maubot/usage/basic.html) to do this. You can download the plugin from the [releases page](https://github.com/rhyst/maubot-weather/releases).

## Usage

Send the following messages to receive a reply from the bot:

- Share a location with the bot for the forecast for that location
- `<lat> <lon>` - Reply with the forecast for the given lat lon
- `version` - Reply with the bot version
- `auth` - Check windy authentication status

Any other message will cause the bot to reply with help text.


## Development

Run:

```
poetry install
```

To produce a build run:

```
poetry run mbc build
```

You can also deploy directly to the maubot instance. First authenticate the maubot instance:

```
poetry run mbc login -u maubot_user -p 'maubot_password' -s https://matrix.example.com -a my_server_alias
```

Then you can build and upload directly with this:

```
poetry run mbc build -u
```

To create a github release tag the version and use the `gh` cli tool:

```
git tag x.x.x
git push --tags
gh release --latest x.x.x xyz.maubot.weather-vx.x.x.mbp
```

