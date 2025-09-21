# ~/~ begin <<docs/index.md#src/repl_session/__init__.py>>[init]
#| file: src/repl_session/__init__.py
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""
# ~/~ begin <<docs/index.md#imports>>[init]
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
# ~/~ end

# ~/~ begin <<README.md#input-data>>[init]
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
# ~/~ end
# ~/~ begin <<README.md#input-data>>[1]
#| id: input-data
class ReplCommand(msgspec.Struct):
    """A command to be sent to the REPL.

    Attributes:
        command (str): the command.
        output_type (str): MIME type of expected output.
        output (str | None): evaluated output.
        expected (str | None): expected output.
    """
    command: str
    output_type: str = "text/plain"
    output: str | None = None
    expected: str | None = None


class ReplSession(msgspec.Struct):
    """A REPL session.

    Attributes:
        config (ReplConfig): Config for setting up a REPL session.
        commands (list[ReplCommand]): List of commands in the session.
    """
    config: ReplConfig
    commands: list[ReplCommand]
# ~/~ end

# ~/~ begin <<docs/index.md#repl-contextmanager>>[init]
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
# ~/~ end
# ~/~ begin <<docs/index.md#run-session>>[init]
#| id: run-session
def run_session(session: ReplSession):
    with repl(session.config) as run:
        for cmd in session.commands:
            expected = cmd.expected or cmd.output
            output = run(cmd.command)
            cmd.output = output
            cmd.expected = expected

    return session
# ~/~ end
# ~/~ begin <<docs/index.md#io>>[init]
#| id: io

def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: str = port.read()
    return msgspec.yaml.decode(data, type=ReplSession)


def write_session(session: ReplSession, port: IO[str] = sys.stdout):
    data = msgspec.json.encode(session)
    port.write(data.decode())
# ~/~ end


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
# ~/~ end
