# ~/~ begin <<docs/index.md#src/repl_session/__init__.py>>[init]
"""
`repl-session` is a command-line tool to evaluate a given session
in any REPL, and store the results.
"""

# ~/~ begin <<docs/index.md#imports>>[init]
# from datetime import datetime, tzinfo
from typing import IO, cast
from collections.abc import Generator, Callable

# import re
from contextlib import contextmanager
import uuid
import sys
import re
import logging
import os

import pexpect
import msgspec
import click
import importlib.metadata


__version__ = importlib.metadata.version("repl-session")
# ~/~ end
# ~/~ begin <<README.md#input-data>>[init]
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
def spawn(config: ReplConfig):
    env = dict(os.environ) | config.environment
    child: pexpect.spawn[str] = pexpect.spawn(
        config.command,
        timeout=config.timeout,
        echo=False,
        encoding="utf-8",
        env=dict(os.environ) | config.environment,
    )
    return child


ANSI_ESCAPE = re.compile(r"(\u001b|\x1B)(\[[0-?]*[ -\/]*[@-~]|[\>\=])")


def clean_output(config: ReplConfig, output: str) -> str | None:
    """Remove ANSI escapes (if requested), normalize the CRLF line endings
    that the pseudo-terminal produces, and trim surrounding whitespace.
    Returns `None` if nothing is left."""
    if config.strip_ansi:
        output = ANSI_ESCAPE.sub("", output)
    output = output.replace("\r\n", "\n").replace("\r", "").strip()
    return output or None


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
                    logging.debug("sending: '%s'", line)
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
                    _ = child.sendline("")
                    _ = child.expect(prompt)
                    logging.debug(f"got: %s", child.before)
                    if child.before:
                        answer.append(child.before)

                if not answer:
                    return None

                return clean_output(config, answer[-1])

        else:
            def send(msg: str) -> str | None:
                logging.debug("sending: %s", msg)

                _ = child.sendline(msg)
                _ = child.expect(prompt)

                if not child.before:
                    return None

                return clean_output(config, child.before)

        yield send
# ~/~ end
# ~/~ begin <<docs/index.md#run-session>>[init]
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
def read_session(port: IO[str] = sys.stdin) -> ReplSession:
    data: str = port.read()
    return msgspec.yaml.decode(data, type=ReplSession)


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
