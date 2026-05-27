import argparse
import asyncio
import signal

import pytest

import marstek_ble_mqtt.cli as cli
from marstek_ble_mqtt.cli import build_parser


def test_public_cli_is_minimal() -> None:
    parser = build_parser()

    run_args = parser.parse_args(["run", "--config", "config.example.toml"])
    stdout_args = parser.parse_args(["run", "--config", "config.example.toml", "--stdout"])
    profiles_args = parser.parse_args(["profiles"])

    assert run_args.command == "run"
    assert not hasattr(run_args, "once")
    assert not hasattr(run_args, "pretty")
    assert stdout_args.command == "run"
    assert stdout_args.stdout is True
    assert profiles_args.command == "profiles"
    assert not hasattr(profiles_args, "json")


def test_run_unknown_arguments_hint_at_config_and_environment(capsys) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--address", "AA:BB:CC:DD:EE:FF"])

    error = capsys.readouterr().err
    assert "unrecognized arguments: --address AA:BB:CC:DD:EE:FF" in error
    assert "Runtime settings belong in config.toml or environment variables" in error


def test_debug_scan_command_is_namespaced() -> None:
    parser = build_parser()

    args = parser.parse_args(["debug", "scan", "--timeout", "1"])

    assert args.command == "debug"
    assert args.debug_command == "scan"
    assert args.timeout == 1
    assert not hasattr(args, "json")


def test_debug_services_command_is_namespaced() -> None:
    parser = build_parser()

    args = parser.parse_args(["debug", "services", "--address", "AA:BB:CC:DD:EE:FF"])

    assert args.command == "debug"
    assert args.debug_command == "services"
    assert args.address == "AA:BB:CC:DD:EE:FF"
    assert not hasattr(args, "connect_timeout")
    assert not hasattr(args, "skip_reads")
    assert not hasattr(args, "json")


def test_run_stop_state_maps_signals_to_exit_codes() -> None:
    sigint_state = cli._RunStopState(stop_event=asyncio.Event())
    sigterm_state = cli._RunStopState(stop_event=asyncio.Event())

    sigint_state.request_signal(signal.SIGINT)
    sigterm_state.request_signal(signal.SIGTERM)

    assert sigint_state.reason == "SIGINT"
    assert sigint_state.exit_code == 130
    assert sigint_state.stop_event.is_set()
    assert sigterm_state.reason == "SIGTERM"
    assert sigterm_state.exit_code == 143
    assert sigterm_state.stop_event.is_set()


def test_run_command_uses_signal_stop_adapters(monkeypatch) -> None:
    class NoopSignalHandlers:
        def close(self) -> None:
            pass

    def fake_install_handlers(state: cli._RunStopState) -> NoopSignalHandlers:
        state.request_signal(signal.SIGTERM)
        return NoopSignalHandlers()

    async def fake_run_bridge(_options, adapters) -> int:
        assert adapters.stop_event.is_set()
        assert adapters.stop_reason() == "SIGTERM"
        return adapters.stop_exit_code()

    monkeypatch.setattr(cli, "_install_run_signal_handlers", fake_install_handlers)
    monkeypatch.setattr(cli, "run_bridge", fake_run_bridge)

    exit_code = asyncio.run(
        cli._run_bridge(
            argparse.Namespace(
                config="config.toml",
                stdout=False,
            )
        )
    )

    assert exit_code == 143
