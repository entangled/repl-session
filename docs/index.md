{% include 'README.md' %}

##  Implementation

The core of the implementation is handled by the `pexpect` library. We have a small wrapper context manager to start the REPL and send commands.

```python
#| id: repl-contextmanager

@contextmanager
def repl(config: ReplConfig) -> Generator[Callable[[str], str]]:
    key = str(uuid.uuid4())

    with pexpect.spawn(config.command, timeout=config.timeout) as child:
        child.expect(config.first_prompt)
        change_prompt_cmd = config.change_prompt.format(key=key)
        if config.append_newline:
            change_prompt_cmd = change_prompt_cmd + "\n"
        child.send(change_prompt_cmd)
        if config.strip_command:
            child.expect(key)
        prompt = config.next_prompt.format(key=key)
        child.expect(prompt)

        def send(msg: str) -> str:
            if config.append_newline:
                msg = msg + "\n"
            child.send(msg)
            child.expect("(.*)" + prompt)

            answer = child.match[1].decode()
            if config.strip_ansi:
                ansi_escape = re.compile(r'(\u001b\[|\x1B\[)[0-?]*[ -\/]*[@-~]')
                answer = ansi_escape.sub("", answer)
            if config.strip_command:
                answer = answer.strip().replace("\r", "")
                return answer.removeprefix(msg)
            else:
                return child.match[1].decode()

        yield send
```

We use this to run a session. The session is modified in place.

```python
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

def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: str = port.read()
    return msgspec.yaml.decode(data, type=ReplSession)


def write_session(session: ReplSession, port: IO[str] = sys.stdout):
    data = msgspec.json.encode(session)
    port.write(data.decode())
```

##  Imports

```python
#| id: imports
# from datetime import datetime, tzinfo
from typing import IO
from collections.abc import Generator, Callable
# import re
from contextlib import contextmanager
import uuid
import sys
import re

import pexpect
import msgspec
import argh
import importlib.metadata


__version__ = importlib.metadata.version("repl-session")
```

## Synthesis

```python
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
def repl_session(version: bool = False):
    """
    repl-session runs a REPL session, reading JSON from standard input and
    writing to standard output. Both the input and output follow the same
    schema.
    """
    if version:
        print(f"repl-session {__version__}")
        sys.exit(0)

    write_session(run_session(read_session()))


def main():
    argh.dispatch_command(repl_session)
```
