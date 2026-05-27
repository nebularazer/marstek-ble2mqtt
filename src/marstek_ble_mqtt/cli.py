"""Command-line interface for marstek-ble2mqtt."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import marstek_ble_mqtt.output as output
from marstek_ble_mqtt.profiles import format_profiles
from marstek_ble_mqtt.runtime import RunOptions, run_bridge
from marstek_ble_mqtt.scanner import format_scan_results, scan_ble_devices
from marstek_ble_mqtt.services import dump_ble_services, format_service_dump

DEFAULT_CONFIG_PATH = Path("config.toml")
RUN_CONFIG_HINT = (
    "Runtime settings belong in config.toml or environment variables; "
    "run only accepts --config and --stdout."
)


class _HintingArgumentParser(argparse.ArgumentParser):
    def parse_args(
        self,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        self._raw_args = tuple(args if args is not None else sys.argv[1:])
        return super().parse_args(args, namespace)

    def error(self, message: str) -> None:
        raw_args = getattr(self, "_raw_args", ())
        is_run_command = bool(raw_args) and raw_args[0] == "run"
        should_hint = getattr(self, "_runtime_config_hint", False) or is_run_command
        if should_hint and message.startswith("unrecognized arguments:"):
            message = f"{message}\n{RUN_CONFIG_HINT}"
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _HintingArgumentParser(
        prog="marstek-ble2mqtt",
        description="Bluetooth-to-MQTT bridge for Marstek/Hame batteries.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=_HintingArgumentParser,
    )

    run_parser = subparsers.add_parser("run", help="Publish BLE telemetry to MQTT.")
    run_parser._runtime_config_hint = True
    _add_config_argument(run_parser)
    run_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print telemetry JSON to stdout instead of publishing to MQTT.",
    )

    subparsers.add_parser("profiles", help="List built-in device profiles.")

    debug_parser = subparsers.add_parser("debug", help="Read-only BLE discovery tools.")
    debug_subparsers = debug_parser.add_subparsers(dest="debug_command", required=True)

    scan_parser = debug_subparsers.add_parser(
        "scan",
        help="Find likely Marstek/Hame BLE devices without connecting.",
    )
    scan_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="BLE scan duration in seconds. Default: 5.",
    )

    services_parser = debug_subparsers.add_parser(
        "services",
        help="Connect once and dump GATT services read-only.",
    )
    services_parser.add_argument("--address", required=True, help="BLE address to inspect.")

    return parser


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to TOML config. Default: config.toml.",
    )


async def _run_debug_scan(args: argparse.Namespace) -> int:
    results = await scan_ble_devices(timeout=args.timeout)
    print(format_scan_results(results))
    likely = [result for result in results if result.is_likely_marstek]
    if likely:
        best = likely[0]
        markers = ", ".join(best.matched_markers) or "name/manufacturer marker"
        print(
            "\nSuggested BLE address: "
            f"{best.address} ({best.name or '<unknown>'}; matched {markers})"
        )
    else:
        print("\nNo likely Marstek/Hame battery advertisement found.")
    return 0


async def _run_debug_services(args: argparse.Namespace) -> int:
    services = await dump_ble_services(
        address=args.address,
    )
    print(format_service_dump(services))
    return 0


async def _run_bridge(args: argparse.Namespace) -> int:
    return await run_bridge(
        RunOptions(
            config_path=args.config,
            stdout=args.stdout,
        )
    )


def _run_profiles(args: argparse.Namespace) -> int:
    print(format_profiles())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            return asyncio.run(_run_bridge(args))
        if args.command == "profiles":
            return _run_profiles(args)
        if args.command == "debug":
            if args.debug_command == "scan":
                return asyncio.run(_run_debug_scan(args))
            if args.debug_command == "services":
                return asyncio.run(_run_debug_services(args))
    except KeyboardInterrupt:
        if args.command == "run":
            output.print_json_event("info", "stopped", reason="keyboard_interrupt")
        else:
            print("Stopped by user.")
        return 130

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
