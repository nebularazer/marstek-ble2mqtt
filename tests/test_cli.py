import pytest

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
