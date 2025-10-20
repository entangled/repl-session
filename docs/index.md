{% include 'README.md' %}

##  Implementation

The core of the implementation is handled by the `pexpect` library. We have a small wrapper context manager to start the REPL and send commands.

```python
#| id: repl-contextmanager
#| id: repl-contextmanager
def spawn(config: ReplConfig):
    child: pexpect.spawn[str] = pexpect.spawn(
        config.command,
        timeout=config.timeout,
        echo=False,
        encoding="utf-8",
        env=config.environment,
    )
    return child


@contextmanager
def repl(config: ReplConfig) -> Generator[Callable[[str], str | None]]:
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
            def send(msg: str) -> str | None:
                lines = msg.splitlines()
                answer: list[str] = []

                if not lines:
                    return None

                still_waiting: bool = True
                for line in lines:
                    logging.debug("sending: %s", line)
                    _ = child.sendline(line)
                    logging.debug("waiting for prompt or continuation")
                    _ = child.expect(
                        f"(?P<norm>{prompt})|(?P<cont>{continuation_prompt})"
                    )
                    if not isinstance(child.match, re.Match):
                        continue
                    if child.match.group("cont") is not None:
                        logging.debug("continuation: %s -- %s", child.before, child.after)
                        still_waiting = True
                    else:
                        logging.debug("done: %s", child.before)
                        if child.before is not None:
                            answer.append(child.before)
                        still_waiting = False

                if still_waiting:
                    logging.debug(f"waiting for last prompt")
                    # _ = child.sendline("")
                    _ = child.expect(prompt)
                    logging.debug(f"got: %s", child.before)
                    if child.before:
                        answer.append(child.before)

                if not answer:
                    return None

                if config.strip_ansi:
                    ansi_escape = re.compile(r"(\u001b\[|\x1B\[)[0-?]*[ -\/]*[@-~]")
                    return ansi_escape.sub("", answer[-1].strip())

                return answer[-1].strip()

        else:
            def send(msg: str) -> str | None:
                logging.debug("sending: %s", msg)

                _ = child.sendline(msg)
                _ = child.expect(prompt)

                answer = child.before.strip()

                if not answer:
                    return None

                if config.strip_ansi:
                    ansi_escape = re.compile(r"(\u001b\[|\x1B\[)[0-?]*[ -\/]*[@-~]")
                    return ansi_escape.sub("", answer)

                return answer

        yield send


```

We use this to run a session. The session is modified in place.

```python
#| id: run-session
#| id: run-session
def run_session(session: ReplSession):
    with repl(session.config) as run:
        for cmd in session.commands:
            expected = cmd.expected or cmd.output
            output = run(cmd.command)
            cmd.output = output
            cmd.expected = expected

    return session


```

### I/O

I/O is handled by `msgspec`.

```python
#| id: io
#| id: io
def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: str = port.read()
    return msgspec.yaml.decode(data, type=ReplSession)


def write_session(session: ReplSession, port: IO[str] = sys.stdout):
    data = msgspec.json.encode(session)
    _ = port.write(data.decode())


```

##  Imports

```python
#| id: imports
#| id: imports
# from datetime import datetime, tzinfo
from typing import IO, cast
from collections.abc import Generator, Callable

# import re
from contextlib import contextmanager
import uuid
import sys
import re
import logging

import pexpect
import msgspec
import argh
import importlib.metadata


__version__ = importlib.metadata.version("repl-session")
```

## Synthesis

```python
#| file: src/repl_session/__init__.py
#| file: src/repl_session/__init__.py
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""

<<imports>>


<<input-data>>


<<repl-contextmanager>>
<<run-session>>
<<io>>


@argh.arg("-v", "--version", help="show version and exit")
@argh.arg("-l", "--log-enable", help="show debugging output")
def repl_session(version: bool = False, log_enable: bool = False):
    """
    repl-session runs a REPL session, reading JSON from standard input and
    writing to standard output. Both the input and output follow the same
    schema.
    """
    if version:
        print(f"repl-session {__version__}")
        sys.exit(0)

    if log_enable:
        logging.basicConfig(level=logging.DEBUG)

    write_session(run_session(read_session()))


def main():
    argh.dispatch_command(repl_session)


```
