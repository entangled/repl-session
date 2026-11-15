# ~/~ begin <<docs/index.md#src/repl_session/repl.py>>[init]
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

# ~/~ begin <<docs/index.md#repl-contextmanager>>[init]
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
# ~/~ end
# ~/~ end
