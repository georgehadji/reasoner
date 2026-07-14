import ast
from pathlib import Path


def test_server_port_default_matches_api_port():
    """SERVER_PORT default in settings.py must match DEFAULT_API_PORT in constants.py."""
    core_dir = Path(__file__).parent.parent / "src" / "reasoner" / "core"

    # Extract SERVER_PORT default from settings.py
    settings_src = (core_dir / "settings.py").read_text(encoding="utf-8")
    settings_tree = ast.parse(settings_src)
    server_port_default = None
    for node in ast.walk(settings_tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "getenv":
            args = [ast.literal_eval(a) for a in node.args]
            if args and args[0] == "SERVER_PORT" and len(args) >= 2:
                server_port_default = args[1]

    # Extract DEFAULT_API_PORT from constants.py
    constants_src = (core_dir / "constants.py").read_text(encoding="utf-8")
    constants_tree = ast.parse(constants_src)
    api_port = None
    for node in ast.walk(constants_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULT_API_PORT":
                    api_port = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "DEFAULT_API_PORT":
                api_port = ast.literal_eval(node.value)

    assert server_port_default is not None, "Could not find SERVER_PORT default in settings.py"
    assert api_port is not None, "Could not find DEFAULT_API_PORT in constants.py"
    assert server_port_default == str(api_port), (
        f"settings.SERVER_PORT default ({server_port_default}) does not match "
        f"DEFAULT_API_PORT ({api_port})"
    )
