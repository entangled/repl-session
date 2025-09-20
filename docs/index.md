# REPL Session

This is a Python script that runs a session on any REPL following a description  in a JSON file. The output contains the commands entered and the results given. This can be useful to drive documentation tests or literate programming tasks. This way we decouple running the commands from rendering or presenting the corresponding results, leading  to better reproducibility, caching output and modularity w.r.t. any other tools that you may use.

This is very similar to running a Jupyter notebook, with the benefit that you don't need a Jupyter kernel available for the language you're using.

## Input/Output structure

The user can configure how the REPL is called and interpreted.

```python
#| id: input-data
class ReplConfig(msgspec.Struct):
    """Command to start the REPL"""
    command: str
    """Regex to match the first prompt"""
    first_prompt: str
    """Command to change prompt; should contain '{key}' as an argument."""
    change_prompt: str
    """Regex to match the changed prompts; should contain '{key}' as an argument."""
    next_prompt: str
    """Whether to append a newline to given commands."""
    append_newline: bool = True
    """Whether to strip the original command from the gotten output; useful if the REPL
    echoes your input before answering."""
    strip_command: bool = False
    """Command timeout for this session in seconds."""
    timeout: float = 5.0
```

Then, a session is a list of commands. Each command should be a UTF-8 string, and we allow to attach some meta-data like expected MIME type for the output. We can also pass an expected output in the case of a documentation test. If `output` was already given on the input, it is  moved to `expected`. This way it becomes really easy to setup regression tests on your documentation. Just rerun on the generated output file.

```python
#| id: input-data
class ReplCommand(msgspec.Struct):
    command: str
    output_type: str = "text/plain"
    output: str | None = None
    expected: str | None = None


@dataclass
class ReplSession(msgspec.Struct):
    config: ReplConfig
    commands: list[ReplCommand]
    # execution_start: datetime | None = None
    # execution_end: datetime | None = None
```

##  Implementation

The core of the implementation is handled by the `pexpect` library. We have a small wrapper context manager to start the REPL and send commands.

```python
#| id: repl-contextmanager

@contextmanager
def repl(config: ReplConfig):
    key = str(uuid.uuid4())
    child = pexpect.spawn(config.command, timeout=config.timeout)
    child.expect(config.first_prompt)
    child.send(config.change_prompt.format(key=key))
    prompt = config.next_prompt.format(key=key)
    child.expect(prompt)

    def send(msg: str) -> re.Match:
        if config.append_newline:
            msg = msg + "\n"
        child.send(msg)
        child.expect("(.*)" + prompt)

        if config.strip_command:
            answer = child.match[1].decode().strip().replace("\r", "")
            return answer.removeprefix(msg)
        else:
            return child.match[1].decode()

    yield send

    child.close()
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

def read_session(port):

```

##  Imports

```python
#| id: imports
from datetime import datetime, tzinfo
from dataclasses import dataclass
from contextlib import contextmanager
import uuid

import pexpect
import msgspec
```

## Synthesis

```python
#| file: repl_session/__init__.py
<<imports>>

<<input-data>>

<<repl-contextmanager>>
<<run-session>>
<<io>>
```
