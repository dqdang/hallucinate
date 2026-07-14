"""System tray icon: pick your visible status, (re)launch a game, quit.

pystray runs its own event loop and expects to own the thread it's given,
so we run it in a background thread and hand status changes back to the
asyncio side through a plain thread-safe callback.
"""
from __future__ import annotations

import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from .riot_client import LAUNCH_PRODUCTS

STATUS_COLORS = {
    "online": (61, 190, 90),
    "away": (240, 170, 40),
    "offline": (140, 140, 140),
    "mobile": (70, 130, 220),
}


def _make_icon_image(status: str) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(30, 30, 30, 255))
    color = STATUS_COLORS.get(status, STATUS_COLORS["offline"])
    draw.ellipse((18, 18, size - 18, size - 18), fill=color + (255,))
    return img


class TrayApp:
    def __init__(
        self,
        initial_status: str,
        on_status_change: Callable[[str], None],
        on_launch_game: Callable[[str], None],
        on_quit: Callable[[], None],
    ):
        self._status = initial_status
        self._on_status_change = on_status_change
        self._on_launch_game = on_launch_game
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            "hallucinate",
            icon=_make_icon_image(initial_status),
            title=f"Hallucinate ({initial_status})",
            menu=self._build_menu(),
        )
        self._thread: threading.Thread | None = None

    def _build_menu(self) -> pystray.Menu:
        def status_item(status: str, label: str):
            return pystray.MenuItem(
                label,
                lambda: self._set_status(status),
                checked=lambda item, s=status: self._status == s,
                radio=True,
            )

        def launch_item(game: str, label: str):
            return pystray.MenuItem(label, lambda: self._on_launch_game(game))

        return pystray.Menu(
            pystray.MenuItem("Status", pystray.Menu(
                status_item("online", "Online"),
                status_item("away", "Away"),
                status_item("mobile", "Mobile"),
                status_item("offline", "Appear offline"),
            )),
            pystray.MenuItem("Launch", pystray.Menu(
                *(launch_item(game, game.upper()) for game in LAUNCH_PRODUCTS)
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _set_status(self, status: str) -> None:
        self._status = status
        self._icon.icon = _make_icon_image(status)
        self._icon.title = f"Hallucinate ({status})"
        self._on_status_change(status)

    def _quit(self) -> None:
        self._icon.stop()
        self._on_quit()

    def run_in_background(self) -> None:
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def notify(self, message: str, title: str = "Hallucinate") -> None:
        try:
            self._icon.notify(message, title)
        except NotImplementedError:
            pass  # not every platform backend supports notifications
