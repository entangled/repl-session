{% include 'README.md' %}

##  Implementation

The core of the implementation is handled by the `pexpect` library. We have a small wrapper context manager to start the REPL and send commands.

```python
#| id: repl-contextmanager
def spawn(config: ReplConfig):
    env = dict(os.environ) | config.environment
    child: pexpect.spawn[str] = pexpect.spawn(
        config.command,
        timeout=config.timeout,
        echo=False,
        encoding="utf-8",
        env=env,
    )
    return child


def clean_output(config: ReplConfig, output: str) -> str | None:
    """Remove ANSI escapes (if requested), normalize the CRLF line endings
    that the pseudo-terminal produces, and trim surrounding whitespace.
    Returns `None` if nothing is left."""
    if config.strip_ansi:
        output = ANSI_ESCAPE.sub("", output)
    output = output.replace("\r\n", "\n").replace("\r", "").strip()
    return output or None


@contextmanager
def repl(config: ReplConfig) -> Generator[Evaluator]:
    key = str(uuid.uuid4())
    change_prompt_cmd = config.change_prompt.format(key=key)
    prompt = config.prompt.format(key=key)
    continuation_prompt = (
        config.continuation_prompt.format(key=key)
        if config.continuation_prompt is not None
        else None
    )

    child: pexpect.spawn[str]
    with spawn(config) as child:
        _ = child.expect(config.first_prompt)
        _ = child.sendline(change_prompt_cmd)
        # if config.strip_command:
        #    child.expect(key)
        _ = child.expect(prompt)

        if continuation_prompt is not None:
            def send_text(msg: str) -> str | None:
                lines = msg.splitlines()
                answer: list[str] = []

                if not lines:
                    return None

                still_waiting: bool = True
                for line in lines:
                    logger.debug("sending: '%s'", line)
                    _ = child.sendline(line)
                    logger.debug("waiting for prompt or continuation")
                    _ = child.expect(
                        f"(?P<norm>{prompt})|(?P<cont>{continuation_prompt})"
                    )
                    if not isinstance(child.match, re.Match):
                        continue
                    if child.match.group("cont") is not None:
                        logger.debug("continuation: %s -- %s", child.before, child.after)
                        still_waiting = True
                    else:
                        logger.debug("done: %s", child.before)
                        if child.before is not None:
                            answer.append(child.before)
                        still_waiting = False

                if still_waiting:
                    logger.debug("waiting for last prompt")
                    _ = child.sendline("")
                    _ = child.expect(prompt)
                    logger.debug("got: %s", child.before)
                    if child.before:
                        answer.append(child.before)

                if not answer:
                    return None

                return clean_output(config, answer[-1])

        else:
            def send_text(msg: str) -> str | None:
                logger.debug("sending: %s", msg)

                _ = child.sendline(msg)
                _ = child.expect(prompt)

                if not child.before:
                    return None

                return clean_output(config, child.before)

        def send(cmd: ReplCommand) -> list[ReplOutput]:
            text = send_text(cmd.command)
            if text is None:
                return []
            return [ReplOutput("result", {cmd.output_type: text})]

        yield send
```

The REPL backend has its own module, `repl_session.repl`, next to `repl_session.jupyter`.

```python
#| file: src/repl_session/repl.py
"""
REPL backend for `repl-session`: drives any interactive REPL through `pexpect`.
"""

from collections.abc import Generator
from contextlib import contextmanager
import uuid
import re
import logging
import os

import pexpect

from .schema import ANSI_ESCAPE, Evaluator, ReplCommand, ReplConfig, ReplOutput

logger = logging.getLogger(__name__)

<<repl-contextmanager>>
```

Each backend is a context manager that yields an `Evaluator`. An `Evaluator` takes a `ReplCommand` and returns a list of `ReplOutput`. The `repl` backend above returns at most one output, holding the terminal text under the command's `output_type`. The [Jupyter backend](jupyter.md) is optional and is imported only when a session asks for it.

We use this to run a session. The session is modified in place. The full output goes into `outputs`, and the representation matching `output_type` is copied to `output`.

```python
#| id: run-session
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
```

### I/O

I/O is handled by `msgspec`.

```python
#| id: io
def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: Any = msgspec.yaml.decode(port.read())
    # Sessions written before there were multiple backends have no `backend` tag.
    if isinstance(data, dict) and isinstance(config := data.get("config"), dict):
        _ = config.setdefault("backend", "repl")
    return msgspec.convert(data, type=ReplSession)


def write_session(session: ReplSession, port: IO[str] = sys.stdout):
    data = msgspec.json.encode(session)
    _ = port.write(data.decode())
```

##  Imports

```python
#| id: imports
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
```

## Schema

The data types live in a separate module, `repl_session.schema`. Both backends import from it. The Jupyter backend is loaded lazily from the main module, so if it imported from `repl_session` itself, the two modules would import each other. Besides the session structure, the schema module also defines the `Evaluator` interface that every backend implements, and the regex for ANSI escapes, which both backends use.

```python
#| id: schema-shared
Evaluator = Callable[[ReplCommand], list[ReplOutput]]

ANSI_ESCAPE = re.compile(r"(\u001b|\x1B)(\[[0-?]*[ -\/]*[@-~]|[\>\=])")
```

`JupyterConfig` has to come before `input-data`: `ReplSession` refers to it in an annotation, and annotations are evaluated eagerly before Python 3.14.

```python
#| file: src/repl_session/schema.py
"""
Data types for `repl-session`: the session format and the interface shared
by the backends.
"""

from typing import Any, Literal
from collections.abc import Callable
import re

import msgspec

<<jupyter-config>>
<<input-data>>
<<schema-shared>>
```

## Synthesis

```python
#| file: src/repl_session/__init__.py
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""

<<imports>>
<<run-session>>
<<io>>

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
```
