"""Submodule to demonstrate virtual in-memory imports without disk extraction."""


def make_welcome_banner(player_name: str, server_motd: str) -> str:
    return f"§a[SamplePlugin] §eWelcome §b{player_name}§e! §7({server_motd})"
