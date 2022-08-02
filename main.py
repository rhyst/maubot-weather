import asyncio
import re
from pyppeteer import launch
from mautrix.types import EventType, MessageType, MediaMessageEventContent, ImageInfo
from maubot import Plugin
from maubot.handlers import event


class WeatherBot(Plugin):
    async def forecast(self, latitude, longitude):
        # Scrape Windy multi modal forecast for provided lat/lon
        # Returns a tuple with the place name and message object with the forecast image
        browser = await launch(
            {
                "executablePath": "/usr/bin/chromium-browser",
                "args": ["--no-sandbox", "--headless", "--disable-gpu"],
            }
        )
        page = await browser.newPage()
        await page.goto(f"https://www.windy.com/multimodel/{latitude}/{longitude}")
        await page.setViewport({"width": 1920, "height": 1080})
        await asyncio.sleep(5)
        place = await page.evaluate(
            f"""
            document.querySelector("input").value
        """
        )

        forecast = await page.querySelector("iframe")
        if not forecast:
            return (place, None)
        forecast_image = await forecast.screenshot(
            {
                "clip": {"x": 0, "y": 120, "height": 800, "width": 1245},
            }
        )
        await browser.close()
        uri = await self.client.upload_media(forecast_image, mime_type="image/png")
        return (
            place,
            MediaMessageEventContent(
                url=uri,
                body="weather.png",
                msgtype=MessageType.IMAGE,
                info=ImageInfo(
                    mimetype="image/png",
                    size=len(forecast_image),
                    width=1245,
                    height=800,
                ),
            ),
        )

    @event.on(EventType.ROOM_MESSAGE)
    async def handle_message(self, evt) -> None:
        if evt.sender == self.client.mxid:
            return

        self.log.info(f"Message recieved from {evt.sender}")

        if evt.content.msgtype == MessageType.LOCATION:
            self.log.info(f"Location message recieved from {evt.sender}")
            # Respond to location events with forecast for that location
            await evt.respond("Fetching weather")
            result = re.search(r"geo:([-\d\.]+),([-\d\.]+)", evt.content.geo_uri)
            lat = result.group(1)
            lon = result.group(2)
            place, content = await self.forecast(lat, lon)
            await evt.respond(f"Weather for {place}")
            self.log.info(f"Weather found for {place}")
            if content:
                await self.client.send_message(evt.room_id, content)
            else:
                await evt.respond(f"Forecast did not load")
            return

        if evt.content.msgtype == MessageType.TEXT:
            self.log.info(f"Text message recieved from {evt.sender}")
            # Attempt to parse a lat lon out of any other text message
            result = re.search(r"([-\d\.]+) ([-\d\.]+)", evt.content.body)
            if result and result.group(1) and result.group(2):
                await evt.respond("Fetching weather")
                lat = result.group(1)
                lon = result.group(2)
                self.log.info(f"Parsed lat lon from text message")
                place, content = await self.forecast(lat, lon)
                await evt.respond(f"Weather for {place}")
                self.log.info(f"Weather found for {place}")
                if content:
                    await self.client.send_message(evt.room_id, content)
                else:
                    await evt.respond(f"Forecast did not load")
                return

            # Send the version
            if "version" in evt.content.body:
                self.log.info(f"Version requested")
                await evt.respond(f"Plugin version {self.loader.meta.version.public}")
                return

        # Fallback to instructions
        await evt.respond(
            f'Either share a location with me, or message me the coordinates you want the weather for: "<lat> <lon>".'
        )
