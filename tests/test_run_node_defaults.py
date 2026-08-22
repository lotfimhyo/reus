"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from scripts.run_node import parse_args


def test_node_cli_binds_to_loopback_by_default():
    arguments = parse_args(["--role", "text-node", "--data-dir", "/tmp/reus-node"])

    assert arguments.mtls_host == "127.0.0.1"
    assert arguments.bootstrap_host == "127.0.0.1"
