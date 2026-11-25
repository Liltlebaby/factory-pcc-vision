"""Run a configured AI worker adapter and publish results to Vision Monitor."""

import argparse
import logging
import os
import signal
import threading

from dotenv import load_dotenv

from .worker_client import WorkerClientSettings, WorkerHeartbeatClient, load_provider


def main(argv=None):
    parser = argparse.ArgumentParser(description='Vision Monitor external AI worker')
    parser.add_argument('--once', action='store_true', help='publish one heartbeat and exit')
    arguments = parser.parse_args(argv)
    load_dotenv('rack_ai/.env')
    logging.basicConfig(level=logging.INFO)

    specification = os.getenv('VISION_WORKER_PROVIDER', '')
    provider = load_provider(specification)
    client = WorkerHeartbeatClient(WorkerClientSettings())
    stop = threading.Event()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    client.run(provider, stop, once=arguments.once)


if __name__ == '__main__':
    main()
