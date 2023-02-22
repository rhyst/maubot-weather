import asyncio
import re
from pyppeteer import launch
from mautrix.types import EventType, MessageType, MediaMessageEventContent, ImageInfo
from maubot import Plugin
from maubot.handlers import event, web
from aiohttp.web import Request, Response
from aiohttp import ClientSession


class WeatherBot(Plugin):
    cookie_account_ss = None
    cookie_account_sid = None

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

    async def forecast(self, evt, latitude, longitude):
        # Scrape Windy multi modal forecast for provided lat/lon
        # Returns a tuple with the place name and message object with the forecast image
        browser = await launch(
            {
                "executablePath": "/usr/bin/chromium-browser",
                "args": ["--no-sandbox", "--headless", "--disable-gpu"],
            }
        )
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

        logged_in = await page.querySelector(".avatar-wrapper")
        if logged_in:
            await evt.respond("Logged in")
        else:
            await evt.respond("Not logged in")

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
        login_url = f"{self.webapp_url}/login"

        self.log.info(f"Message recieved from {evt.sender}")

        if evt.content.msgtype == MessageType.LOCATION:
            self.log.info(f"Location message recieved from {evt.sender}")
            # Respond to location events with forecast for that location
            await evt.respond("Fetching weather")
            result = re.search(r"geo:([-\d\.]+),([-\d\.]+)", evt.content.geo_uri)
            lat = result.group(1)
            lon = result.group(2)
            place, content = await self.forecast(evt, lat, lon)
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
                place, content = await self.forecast(evt, lat, lon)
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

            if "auth" in evt.content.body:
                if not self.cookie_account_ss or not self.cookie_account_sid:
                    await evt.respond(
                        f"Not logged in. Visit {login_url} to provide windy credentials."
                    )
                    return
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
                            await evt.respond(
                                f"Credentials invalid. Visit {login_url} to provide windy credentials."
                            )
                            return
                await evt.respond(f"Credentials seem to be okay.")
                return
        # Fallback to instructions
        await evt.respond(
            f'Either share a location with me, or message me the coordinates you want the weather for: "<lat> <lon>". You can also visit {login_url} to provide windy credentials.'
        )
