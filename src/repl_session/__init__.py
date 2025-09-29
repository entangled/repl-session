# ~/~ begin <<docs/index.md#src/repl_session/__init__.py>>[init]
#| file: src/repl_session/__init__.py
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""

# ~/~ begin <<docs/index.md#imports>>[init]
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
    prompt: str
    continuation_prompt: str | None = None
    strip_ansi: bool = False
    environment: dict[str, str] = msgspec.field(default_factory=dict)
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

        def send(msg: str) -> str | None:
            nonlocal prompt, continuation_prompt, change_prompt_cmd
            lines = msg.splitlines()
            answer: list[str] = []

            still_waiting: bool = True
            for line in lines:
                logging.debug("sending: %s", line)
                _ = child.sendline(line)
                if continuation_prompt is not None:
                    logging.debug("waiting for prompt or continuation")
                    _ = child.expect(
                        f"(?P<cont>{continuation_prompt})|(?P<norm>{prompt})"
                    )
                    if not isinstance(child.match, re.Match):
                        continue
                    if child.match.group("cont") is not None:
                        logging.debug("continuation")
                        still_waiting = True
                    else:
                        logging.debug("done: %s", child.before)
                        if child.before is not None:
                            answer.append(child.before)
                        still_waiting = False
                else:
                    logging.debug("waiting for prompt")
                    _ = child.expect(prompt)
                    if child.before:
                        answer.append(child.before)
                    still_waiting = False

            if still_waiting:
                _ = child.sendline("")
                _ = child.expect(prompt)
                if child.before:
                    answer.append(child.before)

            if not answer:
                return None

            if config.strip_ansi:
                ansi_escape = re.compile(r"(\u001b\[|\x1B\[)[0-?]*[ -\/]*[@-~]")
                return ansi_escape.sub("", answer[-1].strip())

            return answer[-1].strip()

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
    _ = port.write(data.decode())


# ~/~ end


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


# ~/~ end
