import asyncio
import re
from typing import Tuple
from pyppeteer import launch
from mautrix.types import (
    EventType,
    RelationType,
    RelatesTo,
    TextMessageEventContent,
    MessageType,
    MediaMessageEventContent,
    ImageInfo,
    MessageEvent,
    Format,
)
from maubot import Plugin
from maubot.handlers import event, web
from aiohttp.web import Request, Response
from aiohttp import ClientSession


class WeatherBot(Plugin):
    cookie_account_ss = None
    cookie_account_sid = None

    async def send_message(self, room_id: str, message: str):
        return await self.client.send_message(
            room_id,
            TextMessageEventContent(
                body=message,
                formatted_body=message,
                msgtype=MessageType.TEXT,
                format=Format.HTML,
            ),
        )

    async def edit_message(self, room_id: str, message_id: str, message: str):
        return await self.client.send_message_event(
            room_id,
            EventType.ROOM_MESSAGE,
            TextMessageEventContent(
                body=message,
                msgtype=MessageType.TEXT,
                relates_to=RelatesTo(
                    rel_type=RelationType.REPLACE,
                    event_id=message_id,
                ),
            ),
        )

    @web.get("/login")
    async def login(self, req: Request) -> Response:
        return Response(
            text="""
                <form action="" method="post">
                    <div>
                        <label for="email">Email: </label>
                        <input name="email" />
                    </div>
                    <div>
                        <label for="password">Password: </label>
                        <input type="password" name="password">
                    </div>
                    <div>
                        <input type="submit" value="Login">
                    </div>
                </form>
                """,
            content_type="text/html",
        )

    @web.post("/login")
    async def post_login(self, req: Request) -> Response:
        data = await req.post()
        email = data["email"]
        password = data["password"]
        async with ClientSession() as session:
            async with session.post(
                "https://account.windy.com/api/login",
                json={"email": email, "password": password},
            ) as resp:
                self.cookie_account_ss = resp.cookies["_account_ss"]
                self.cookie_account_sid = resp.cookies["_account_sid"]

        return Response(
            text="""<p>Success</p>""",
            content_type="text/html",
        )

    async def forecast(
        self, evt: MessageEvent, latitude: str, longitude: str
    ) -> Tuple[dict, MediaMessageEventContent]:
        # Scrape Windy multi modal forecast for provided lat/lon
        # Returns a tuple with the metadata and message object with the forecast image
        message_id = await self.send_message(evt.room_id, "Launching browser...")
        browser = await launch(
            {
                "executablePath": "/usr/bin/chromium-browser",
                "args": ["--no-sandbox", "--headless", "--disable-gpu"],
            }
        )
        await self.edit_message(evt.room_id, message_id, "Loading page...")
        page = await browser.newPage()
        if self.cookie_account_ss and self.cookie_account_sid:
            await page.setExtraHTTPHeaders(
                {
                    "Cookie": f"_account_ss={self.cookie_account_ss.value};_account_sid={self.cookie_account_sid.value}"
                }
            )
        await page.goto(f"https://www.windy.com/multimodel/{latitude}/{longitude}")
        await page.evaluate(
            f"""
            localStorage.setItem('settings_startUpLastStep', '1');
        """
        )
        await page.reload({"waitUntil": ["networkidle0", "domcontentloaded"]})
        await page.setViewport({"width": 1920, "height": 1080})
        await asyncio.sleep(5)
        place = await page.evaluate(
            f"""
            document.querySelector("input").value
        """
        )

        await self.edit_message(evt.room_id, message_id, "Extracting forecast image...")

        forecast = await page.querySelector("iframe")
        if not forecast:
            return (place, None)
        forecast_image = await forecast.screenshot(
            {
                "clip": {"x": 0, "y": 120, "height": 800, "width": 1245},
            }
        )
        logged_in = await page.querySelector(".avatar-wrapper")
        await browser.close()
        await self.edit_message(evt.room_id, message_id, "Storing forecast image...")
        uri = await self.client.upload_media(forecast_image, mime_type="image/png")
        await self.client.redact(evt.room_id, message_id)
        return (
            {"location": place, "authenticated": logged_in},
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

    async def weather(self, evt: MessageEvent, lat: str, lon: str):
        message_id = await self.send_message(evt.room_id, "Fetching weather...")
        meta, content = await self.forecast(evt, lat, lon)
        await self.edit_message(
            evt.room_id,
            message_id,
            f"Weather for {meta.get('location')} {'🔒' if meta.get('authenticated') else '🔓'}",
        )
        self.log.info(f"Weather found for {meta.get('location')}")
        if content:
            await self.client.send_message(evt.room_id, content)
        else:
            await self.send_message(evt.room_id, "Forecast did not load.")
        return

    @event.on(EventType.ROOM_MESSAGE)
    async def handle_message(self, evt: MessageEvent) -> None:
        if evt.sender == self.client.mxid:
            return
        login_url = f"{self.webapp_url}/login"

        self.log.info(f"Message recieved from {evt.sender}")

        if evt.content.msgtype == MessageType.LOCATION:
            self.log.info(f"Location message recieved from {evt.sender}")
            # Respond to location events with forecast for that location
            result = re.search(r"geo:([-\d\.]+),([-\d\.]+)", evt.content.geo_uri)
            return await self.weather(evt, result.group(1), result.group(2))

        if evt.content.msgtype == MessageType.TEXT:
            self.log.info(f"Text message recieved from {evt.sender}")
            # Attempt to parse a lat lon out of any other text message
            result = re.search(r"([-\d\.]+) ([-\d\.]+)", evt.content.body)
            if result and result.group(1) and result.group(2):
                return await self.weather(evt, result.group(1), result.group(2))

            # Send the version
            if "version" in evt.content.body:
                self.log.info(f"Version requested")
                return await self.send_message(
                    evt.room_id, f"Version {self.loader.meta.version.public}"
                )

            if "auth" in evt.content.body:
                if not self.cookie_account_ss or not self.cookie_account_sid:
                    return await self.send_message(
                        evt.room_id,
                        f"""No credentials. Visit <a href="{login_url}">the login page</a> to provide windy credentials.""",
                    )
                async with ClientSession(
                    cookies={
                        "_account_sid": self.cookie_account_sid,
                        "_account_ss": self.cookie_account_ss,
                    }
                ) as session:
                    async with session.get(
                        "https://account.windy.com/api/info"
                    ) as resp:
                        if resp.status != 200:
                            self.cookie_account_sid = None
                            self.cookie_account_ss = None
                            return await self.send_message(
                                evt.room_id,
                                f"""Credentials invalid. Visit <a href="{login_url}">the login page</a> to provide windy credentials.""",
                            )

                return await self.send_message(evt.room_id, f"""Credentials valid.""")

        # Fallback to instructions
        await self.send_message(
            evt.room_id,
            f"""<p>This bot will provide you with a weather forecast from <a>windy.com</a>.</p>
                <p>Available commands:</p>
                <ul>
                    <li>Share a location with the bot to get a forecast for that location</li>
                    <li><code>&lt;lat&gt; &lt;lon&gt;</code> - Get a forecast for these coordinates</li>
                    <li><code>version</code> - Get the version of the plugin</li>
                    <li><code>auth</code> - Check if the plugin is logged in to Windy.com</li>
                </ul>
                <p>You can also visit <a href="{login_url}">the login page</a> to provide credentials for <a>windy.com</a> which will enable more features (such as 1 hour forecasts) if you have a premium account.
                </p>""".replace(
                "\n", ""
            ),
        )
