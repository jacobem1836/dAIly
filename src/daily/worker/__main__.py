"""Entrypoint: `python -m daily.worker` — registers with the LiveKit server."""
import logging
import os

from livekit.agents import WorkerOptions, cli

from daily.config import Settings
from daily.worker.agent import entrypoint


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    # livekit-agents reads LIVEKIT_URL/API_KEY/API_SECRET from env; surface them
    # explicitly so a misconfigured deployment fails fast.
    os.environ.setdefault("LIVEKIT_URL", settings.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", settings.livekit_api_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", settings.livekit_api_secret)

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
