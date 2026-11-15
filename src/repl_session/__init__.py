# ~/~ begin <<docs/index.md#src/repl_session/__init__.py>>[init]
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""

# ~/~ begin <<docs/index.md#imports>>[init]
# from datetime import datetime, tzinfo
from typing import IO, Any

# import re
from contextlib import AbstractContextManager
import sys
import logging

import msgspec
import click
import importlib.metadata

from .schema import (
    Evaluator,
    JupyterConfig,
    OutputKind,
    ReplCommand,
    ReplConfig,
    ReplOutput,
    ReplSession,
)
from .repl import repl

__all__ = [
    "Evaluator",
    "JupyterConfig",
    "OutputKind",
    "ReplCommand",
    "ReplConfig",
    "ReplOutput",
    "ReplSession",
    "evaluator",
    "read_session",
    "repl",
    "run_session",
    "select_output",
    "write_session",
]

__version__ = importlib.metadata.version("repl-session")
# ~/~ end
# ~/~ begin <<docs/index.md#run-session>>[init]
def evaluator(config: ReplConfig | JupyterConfig) -> AbstractContextManager[Evaluator]:
    """Start the backend selected by `config`. The Jupyter backend is only
    imported when needed, so its dependencies remain optional."""
    if isinstance(config, JupyterConfig):
        from .jupyter import kernel

        return kernel(config)
    return repl(config)


def select_output(outputs: list[ReplOutput], output_type: str) -> str | None:
    """Pick the representation of type `output_type` from the outputs. Text
    is concatenated in order; for other types the last one wins."""
    values = [out.data[output_type] for out in outputs if output_type in out.data]
    if not values:
        return None
    if output_type.startswith("text/"):
        return "\n".join(v.strip("\n") for v in values).strip() or None
    return values[-1]


def run_session(session: ReplSession):
    with evaluator(session.config) as run:
        for cmd in session.commands:
            expected = cmd.expected or cmd.output
            cmd.outputs = run(cmd)
            cmd.output = select_output(cmd.outputs, cmd.output_type)
            cmd.expected = expected

    return session
# ~/~ end
# ~/~ begin <<docs/index.md#io>>[init]
def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: Any = msgspec.yaml.decode(port.read())
    # Sessions written before there were multiple backends have no `backend` tag.
    if isinstance(data, dict) and isinstance(config := data.get("config"), dict):
        _ = config.setdefault("backend", "repl")
    return msgspec.convert(data, type=ReplSession)


def write_session(session: ReplSession, port: IO[str] = sys.stdout):
    data = msgspec.json.encode(session)
    _ = port.write(data.decode())
# ~/~ end

@click.command()
@click.version_option(
    __version__, "-v", "--version",
    prog_name="repl-session", message="%(prog)s %(version)s",
    help="show version and exit")
@click.option("-l", "--log-enable", is_flag=True, help="show debugging output")
def repl_session(log_enable: bool = False):
    """
    repl-session runs a REPL session, reading JSON from standard input and
    writing to standard output. Both the input and output follow the same
    schema.
    """
    if log_enable:
        logging.basicConfig(level=logging.DEBUG)

    write_session(run_session(read_session()))


def main():
    repl_session()
# ~/~ end
