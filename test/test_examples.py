"""Run the example sessions from the README and check their outputs."""

import importlib.util
import os
import shlex
import shutil
from pathlib import Path

import pytest

from repl_session import ReplConfig, ReplSession, read_session, run_session


TEST_DIR = Path(__file__).parent


EXPECTED = {
    "scheme": ["42", None, "3628800"],
    "lua": ["42", "Hello, World!", None, "3628800"],
    "python": ["Hello, World!", "42", None, "3628800"],
}


def load_session(name: str) -> ReplSession:
    with open(TEST_DIR / f"{name}.yml") as f:
        return read_session(f)


def require(available: bool, what: str):
    if available:
        return
    # In CI everything must be available; locally we allow skipping.
    if os.environ.get("CI"):
        pytest.fail(f"{what} not found")
    pytest.skip(f"{what} not found")


@pytest.mark.parametrize("name", EXPECTED.keys())
def test_example(name: str):
    session = load_session(name)
    assert isinstance(session.config, ReplConfig)
    executable = shlex.split(session.config.command)[0]
    require(shutil.which(executable) is not None, f"`{executable}`")

    result = run_session(session)
    assert [cmd.output for cmd in result.commands] == EXPECTED[name]


def test_jupyter():
    require(
        importlib.util.find_spec("jupyter_client") is not None
        and importlib.util.find_spec("ipykernel") is not None,
        "`jupyter_client` and `ipykernel`",
    )
    result = run_session(load_session("jupyter"))
    hello, answer, define, fac, html, error = result.commands

    assert [cmd.output for cmd in (hello, answer, define, fac, html)] == [
        "Hello, World!", "42", None, "3628800", "<b>Hello</b>, World!"
    ]
    assert [[out.kind for out in cmd.outputs or []] for cmd in result.commands] == [
        ["stdout"], ["result"], [], ["result"], ["result"], ["error"]
    ]
    assert html.outputs and set(html.outputs[0].data) == {"text/plain", "text/html"}
    assert error.output and error.output.endswith("ZeroDivisionError: division by zero")
