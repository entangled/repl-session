# ~/~ begin <<docs/index.md#src/repl_session/schema.py>>[init]
"""
Data types for `repl-session`: the session format and the interface shared
by the backends.
"""

from typing import Any, Literal
from collections.abc import Callable
import re

import msgspec

# ~/~ begin <<docs/jupyter.md#jupyter-config>>[init]
class JupyterConfig(msgspec.Struct, tag_field="backend", tag="jupyter"):
    """Configuration for the Jupyter backend; selected with `backend: jupyter`.

    Attributes:
        kernel (str): Name of the Jupyter kernel, see `jupyter kernelspec list`.
        timeout (float): Command timeout in seconds.
        startup_timeout (float): Timeout for starting the kernel in seconds.
        cwd (str | None): Working directory of the kernel.
        environment (dict[str, str]): Extra environment variables for the kernel.
    """

    kernel: str
    timeout: float = 30.0
    startup_timeout: float = 60.0
    cwd: str | None = None
    environment: dict[str, str] = msgspec.field(default_factory=dict)
# ~/~ end
# ~/~ begin <<README.md#input-data>>[init]
class ReplConfig(msgspec.Struct, tag_field="backend", tag="repl"):
    """Configuration for the `pexpect` backend; selected with `backend: repl`,
    which is also the default when `backend` is absent.

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
OutputKind = Literal["result", "display", "stdout", "stderr", "error"]


class ReplOutput(msgspec.Struct, omit_defaults=True):
    """A single piece of output produced by a command.

    Attributes:
        kind (str): One of `result` (the value of the command), `display`
            (rich output produced along the way, e.g. a plot), `stdout`,
            `stderr` or `error` (a traceback). The `repl` backend cannot tell
            these apart and reports everything as a single `result`.
        data (dict[str, str]): MIME bundle: the same output in one or more
            representations, keyed by MIME type. Binary data is base64 encoded;
            JSON data is serialized to a string.
        metadata (dict[str, Any]): Per MIME type metadata, e.g. image sizes.
    """

    kind: OutputKind
    data: dict[str, str]
    metadata: dict[str, Any] = msgspec.field(default_factory=dict)


class ReplCommand(msgspec.Struct):
    """A command to be sent to the REPL.

    Attributes:
        command (str): the command.
        output_type (str): MIME type of expected output.
        output (str | None): evaluated output for `output_type`.
        expected (str | None): expected output.
        outputs (list[ReplOutput] | None): everything the command produced, in
            order, with all available MIME types.
    """

    command: str
    output_type: str = "text/plain"
    output: str | None = None
    expected: str | None = None
    outputs: list[ReplOutput] | None = None


class ReplSession(msgspec.Struct):
    """A REPL session.

    Attributes:
        config (ReplConfig | JupyterConfig): Config for setting up a REPL
            session, the `backend` field selects which.
        commands (list[ReplCommand]): List of commands in the session.
    """

    config: ReplConfig | JupyterConfig
    commands: list[ReplCommand]
# ~/~ end
# ~/~ begin <<docs/index.md#schema-shared>>[init]
Evaluator = Callable[[ReplCommand], list[ReplOutput]]

ANSI_ESCAPE = re.compile(r"(\u001b|\x1B)(\[[0-?]*[ -\/]*[@-~]|[\>\=])")
# ~/~ end
# ~/~ end
