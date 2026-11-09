"""Run the example sessions from the README and check their outputs."""

import os
import shlex
import shutil
from pathlib import Path

import msgspec
import pytest

from repl_session import ReplSession, run_session


TEST_DIR = Path(__file__).parent


EXPECTED = {
    "scheme": ["42", None, "3628800"],
    "lua": ["42", "Hello, World!", None, "3628800"],
    "python": ["Hello, World!", "42", None, "3628800"],
}


def load_session(name: str) -> ReplSession:
    data = (TEST_DIR / f"{name}.yml").read_bytes()
    return msgspec.yaml.decode(data, type=ReplSession)


@pytest.mark.parametrize("name", EXPECTED.keys())
def test_example(name: str):
    session = load_session(name)
    executable = shlex.split(session.config.command)[0]
    if shutil.which(executable) is None:
        # In CI every interpreter must be available; locally we allow skipping.
        if os.environ.get("CI"):
            pytest.fail(f"`{executable}` not found")
        pytest.skip(f"`{executable}` not found")

    result = run_session(session)
    assert [cmd.output for cmd in result.commands] == EXPECTED[name]
