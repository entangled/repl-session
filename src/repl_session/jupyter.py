# ~/~ begin <<docs/jupyter.md#src/repl_session/jupyter.py>>[init]
"""
Jupyter backend for `repl-session`. Requires the `jupyter` extra.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
import logging
import os

import msgspec

try:
    from jupyter_client.manager import start_new_kernel
except ImportError as e:
    raise ImportError(
        "The Jupyter backend needs the `jupyter` extra: "
        "`pip install repl-session[jupyter]`"
    ) from e

from .schema import ANSI_ESCAPE, Evaluator, JupyterConfig, ReplCommand, ReplOutput

logger = logging.getLogger(__name__)

# ~/~ begin <<docs/jupyter.md#jupyter-collect>>[init]
def mime_bundle(data: dict[str, Any]) -> dict[str, str]:
    return {
        mime: value if isinstance(value, str) else msgspec.json.encode(value).decode()
        for mime, value in data.items()
    }


class OutputCollector:
    """Collects IOPub messages into a list of `ReplOutput`."""

    def __init__(self):
        self.outputs: list[ReplOutput] = []
        self.clear_pending: bool = False

    def append(self, output: ReplOutput):
        if self.clear_pending:
            self.outputs.clear()
            self.clear_pending = False

        last = self.outputs[-1] if self.outputs else None
        if (
            last is not None
            and output.kind in ("stdout", "stderr")
            and last.kind == output.kind
        ):
            last.data["text/plain"] += output.data["text/plain"]
        else:
            self.outputs.append(output)

    def __call__(self, msg: dict[str, Any]):
        msg_type = msg["header"]["msg_type"]
        content = msg["content"]
        match msg_type:
            case "stream":
                self.append(ReplOutput(content["name"], {"text/plain": content["text"]}))
            case "execute_result" | "display_data":
                kind = "result" if msg_type == "execute_result" else "display"
                self.append(
                    ReplOutput(kind, mime_bundle(content["data"]), content.get("metadata", {}))
                )
            case "error":
                traceback = ANSI_ESCAPE.sub("", "\n".join(content["traceback"]))
                self.append(ReplOutput("error", {"text/plain": traceback}))
            case "clear_output":
                if content.get("wait"):
                    self.clear_pending = True
                else:
                    self.outputs.clear()
            case _:
                logger.debug("ignoring %s message", msg_type)
# ~/~ end
# ~/~ begin <<docs/jupyter.md#jupyter-kernel>>[init]
@contextmanager
def kernel(config: JupyterConfig) -> Generator[Evaluator]:
    km, kc = start_new_kernel(
        startup_timeout=config.startup_timeout,
        kernel_name=config.kernel,
        cwd=config.cwd,
        env=dict(os.environ) | config.environment,
    )

    def send(cmd: ReplCommand) -> list[ReplOutput]:
        logger.debug("executing: %s", cmd.command)
        collect = OutputCollector()
        _ = kc.execute_interactive(
            cmd.command,
            timeout=config.timeout,
            output_hook=collect,
            allow_stdin=False,
        )
        return collect.outputs

    try:
        yield send
    finally:
        kc.stop_channels()
        km.shutdown_kernel(now=True)
# ~/~ end
# ~/~ end
