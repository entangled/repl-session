# REPL Session

This is a Python script that runs a session on any REPL following a description  in a JSON file. The output contains the commands entered and the results given. This can be useful to drive documentation tests or literate programming tasks. This way we decouple running the commands from rendering or presenting the corresponding results, leading  to better reproducibility, caching output and modularity w.r.t. any other tools that you may use.

This is very similar to running a Jupyter notebook, with the benefit that you don't need a Jupyter kernel available for the language you're using.

## Examples

### Chez Scheme

I like to work with [Chez Scheme](https://cisco.github.io/ChezScheme/). Suppose I want to document an interactive session. This can be done:

```yaml
#| file: test/scheme.yml
config:
    command: "scheme --eedisable"
    first_prompt: "> "
    change_prompt: "(waiter-prompt-string \"{key}>\")"
    next_prompt: "{key}> "
    strip_command: true
commands:
   - command: (* 6 7)
   - command: |
      (define (fac n init)
        (if (zero? n)
          init
          (fac (- n 1) (* init n)))))
   - command: (fac 10 1)
```

Passing this to `repl-session`, it will start the Chez Scheme interpreter, waiting for the `>` prompt to appear. It then changes the prompt to a generated `uuid4` code, for instance `27e87a8a-742c-4501-b05d-b05814f5a010> `. This will make sure that we can't accidentally match something else for an interactive prompt (imagine we're generating some XML!). Since commands are also echoed to standard out, we need to strip them from the resulting output. Running this should give:

```bash
repl-session < test/scheme.yml | jq '.commands.[].output'
```

```
"42"
"(define (fac n init)\n  (if (zero? n)\n    init\n    (fac (- n 1) (* init n)))))"
"3628800"
```

### Lua

This looks very similar to the previous example:

```yaml
#| file: test/lua.yml
config:
    command: "lua"
    first_prompt: "> "
    change_prompt: "_PROMPT = \"{key}> \""
    next_prompt: "{key}> "
    strip_command: true
    strip_ansi: true
commands:
   - command: 6 * 7
   - command: "\"Hello\" .. \", \" .. \"World!\""
```

The Lua REPL is not so nice. It sends ANSI escape codes and those need to be filtered out.

```bash
repl-session < test/lua.yml | jq '.commands.[].output'
```

```
"42"
"Hello, World!"
```

## Input/Output structure

The user can configure how the REPL is called and interpreted.

```python
#| id: input-data
class ReplConfig(msgspec.Struct):
    """Configuration

    Attributes:
        command (str): Command to start the REPL
        first_prompt (str): Regex to match the first prompt
        change_prompt (str): Command to change prompt; should contain '{key}' as an
            argument.
        next_prompt (str): Regex to match the changed prompts; should contain '{key}'
            as an argument.
        append_newline (bool): Whether to append a newline to given commands.
        strip_command (bool): Whether to strip the original command from the gotten
            output; useful if the REPL echoes your input before answering.
        timeout (float): Command timeout for this session in seconds.
    """
    command: str
    first_prompt: str
    change_prompt: str
    next_prompt: str
    append_newline: bool = True
    strip_command: bool = False
    strip_ansi: bool = False
    timeout: float = 5.0
```

Then, a session is a list of commands. Each command should be a UTF-8 string, and we allow to attach some meta-data like expected MIME type for the output. We can also pass an expected output in the case of a documentation test. If `output` was already given on the input, it is  moved to `expected`. This way it becomes really easy to setup regression tests on your documentation. Just rerun on the generated output file.

```python
#| id: input-data
class ReplCommand(msgspec.Struct):
    """A command to be sent to the REPL."""
    command: str
    """Output MIME type; convenient if results are later rendered."""
    output_type: str = "text/plain"
    """Resulting output will be placed here. If this has a value before running,
    the contents are moved to the `expected` member."""
    output: str | None = None
    """Expected output in case of a doc-test."""
    expected: str | None = None


class ReplSession(msgspec.Struct):
    """Config for setting up a REPL session."""
    config: ReplConfig
    """List of commands."""
    commands: list[ReplCommand]
```

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
#| file: repl_session/__init__.py
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
