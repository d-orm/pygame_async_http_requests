import asyncio
import base64
import json
import random
import platform
import sys
from io import BytesIO
from typing import Literal
from urllib.parse import urlencode

import pygame
from PIL import Image

JS_CODE = """
async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function makeRequest() {
  await sleep(<|DELAY|>); // simulate a long response - remove in real use cases

  const fetch_args = {
    method: <|REQUEST_TYPE|>, // <|ARG|> format used for Python string.replace() 
    headers: <|HEADERS|>
    };

  if (<|BODY|>) {
    fetch_args.body = JSON.stringify(<|BODY|>);
  }

  const response = await fetch(<|URL|>, fetch_args);

  if (!response.ok) {
    throw new Error(`HTTP error! Status: ${response.status}`);
  }

  const arrayBuffer = await response.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  const base64String = btoa(String.fromCharCode.apply(null, bytes));

  return base64String;
}

async function callMakeRequest() {
  try {
    const data = await makeRequest();
    window.response_<|REQUEST_ID|> = data;
    console.log('Data:', data);
  } catch (error) {
    console.error('Error:', error);
  }
}

callMakeRequest();
"""


class RequestHandler:
    def __init__(self):
        self._is_web: bool = sys.platform in ("emscripten", "wasi")
        self._js_code: str = JS_CODE
        self._request_tasks: dict[str, asyncio.Task] = {}
        if self._is_web:
            self._window = platform.window
        else:
            import httpx

            self._httpx_client = httpx.AsyncClient()
            self._httpx_responses = {}

    async def _make_request(
        self,
        request_id: int,
        request_type: Literal["POST", "GET"],
        url: str,
        headers: dict,
        params: dict,
        body: dict | None,
    ):
        if self._is_web:
            self._window.eval(
                self._js_code.replace("<|REQUEST_ID|>", str(request_id))
                .replace("<|REQUEST_TYPE|>", f'"{request_type}"')
                .replace("<|URL|>", f'"{url}?{urlencode(params)}"')
                .replace("<|HEADERS|>", json.dumps(headers))
                .replace("<|BODY|>", json.dumps(body) if body else "null")
                .replace("<|DELAY|>", str(random.randint(4, 5) * 1000))
            )
        else:
            kwargs = {
                "method": request_type,
                "url": url,
                "headers": headers,
                "params": params,
            }
            if body:
                kwargs["json"] = body

            try:
                response = await self._httpx_client.request(**kwargs)
                await asyncio.sleep(random.randint(4, 5))  # simulate a long response - remove in real use cases
                self._httpx_responses[request_id] = base64.encodebytes(response.content)
            except Exception as e:
                print(e)
                self._httpx_responses[request_id] = str(e)

    def response(self, request_id: int) -> str:
        if request_id in self._request_tasks and self._request_tasks[request_id].done():
            if self._is_web:
                resp = self._window.eval(f"window.response_{request_id}")
                if resp is not None:
                    return str(resp)
            else:
                return self._httpx_responses[request_id]

    async def post(
        self,
        request_id: int,
        url: str,
        headers: dict = {},
        params: dict = {},
        body: dict = {},
    ):
        self._request_tasks[request_id] = asyncio.create_task(
            self._make_request(request_id, "POST", url, headers, params, body)
        )

    async def get(
        self, request_id: int, url: str, headers: dict = {}, params: dict = {}
    ):
        self._request_tasks[request_id] = asyncio.create_task(
            self._make_request(request_id, "GET", url, headers, params, None)
        )


async def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 26)
    request_handler = RequestHandler()
    running = True
    elapsed_time = 0

    test_post_request_params = {
        "url": "https://httpbin.org/post",
        "headers": {"Content-Type": "application/json"},
        "body": {"test_field_string": "Some test string", "test_field_int": 30},
    }
    test_post_request_params_2 = {
        "url": "https://httpbin.org/post",
        "headers": {"Content-Type": "application/json"},
        "body": {"test_field_string2": "Some test string2", "test_field_int2": 32},
    }
    test_get_request_params = {
        "url": "https://httpbin.org/get",
        "headers": {"Content-Type": "application/json"},
    }
    test_get_image_params = {
        "url": "https://httpbin.org/image/jpeg",
        "headers": {"Content-Type": "image/jpeg"},
    }

    request_made = False
    response_received = False

    while running:
        clock.tick(120)
        elapsed_time += clock.get_time() / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        if not request_made:
            await request_handler.post(request_id=0, **test_post_request_params)
            await request_handler.post(request_id=1, **test_post_request_params_2)
            await request_handler.get(request_id=2, **test_get_request_params)
            await request_handler.get(request_id=3, **test_get_image_params)

            data = "Waiting for responses..."
            text_response_surf = font.render(data, True, (255, 255, 255))
            image_response_surf = font.render(data, True, (255, 255, 255))

            request_made = True

        if not response_received:
            responses = [
                request_handler.response(request_id=0),
                request_handler.response(request_id=1),
                request_handler.response(request_id=2),
                request_handler.response(request_id=3),
            ]
            if all(responses):
                result_string = ""

                for request_id, response in enumerate(responses):
                    data = base64.b64decode(response)
                    if request_id < 2:
                        json_data = json.loads(data)
                        result_string += json_data["data"] + "\n"
                    elif request_id == 2:
                        json_data = json.loads(data)
                        result_string += str(json_data["url"]) + "\n"
                    elif request_id == 3:
                        image = Image.open(BytesIO(data)).convert("RGBA")

                text_response_surf = font.render(result_string, True, (255, 255, 255))
                image_response_surf = pygame.image.frombytes(
                    image.tobytes(), image.size, "RGBA"
                )

                response_received = True

        screen.fill((0, 0, 100))

        fps_surf = font.render(
            f"FPS: {clock.get_fps():0.0f} - elapsed time: {elapsed_time:0.0f}",
            True,
            (255, 255, 255),
        )

        screen.blit(fps_surf, (0, 0))
        screen.blit(text_response_surf, (0, 40))
        screen.blit(image_response_surf, (0, 200))

        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
