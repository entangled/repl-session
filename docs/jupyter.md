# Jupyter backend

The `pexpect` backend works with any REPL, but scraping a terminal has limits. You only get text, you can't tell a return value from printed output or an error, and you have to fight prompts and ANSI codes. If a [Jupyter kernel](https://github.com/jupyter/jupyter/wiki/Jupyter-kernels) is available for your language, it's the better option. Kernels speak a well-defined protocol and return *rich* output: one result may come in several representations at once (say `text/plain`, `text/html` and `image/png`), and the client picks the one it can render.

The Jupyter backend is optional, so the core of `repl-session` stays small. Install it with,

```bash
pip install repl-session[jupyter]
```

This pulls in `jupyter-client`. You also need a kernel, for instance `ipykernel` for Python.

## Example

A session selects the Jupyter backend with `backend: jupyter` and names a kernel, as listed by `jupyter kernelspec list`.

```yaml
#| file: test/jupyter.yml
config:
  backend: jupyter
  kernel: python3
commands:
  - command: print("Hello, World!")
  - command: 6 * 7
  - command: |
      def fac(n):
          for i in range(1, n):
              n *= i
          return n
  - command: fac(10)
  - command: |
      from IPython.display import HTML
      HTML("<b>Hello</b>, World!")
    output_type: text/html
  - command: 1 / 0
```

The `output` field holds the representation requested by `output_type`, exactly as with the `repl` backend:

```bash
repl-session < test/jupyter.yml | jq '.commands.[].output'
```

```
"Hello, World!"
"42"
null
"3628800"
"<b>Hello</b>, World!"
"---------------------------------------------------------------------------\nZeroDivisionError ..."
```

The `outputs` field holds everything the kernel sent back, in order and with all of its representations. For the `HTML` command it looks like this:

```json
[
  {
    "kind": "result",
    "data": {
      "text/plain": "<IPython.core.display.HTML object>",
      "text/html": "<b>Hello</b>, World!"
    }
  }
]
```

## Configuration

Like `ReplConfig`, the configuration is a tagged `msgspec` struct. The `backend` field selects between them.

```python
#| id: jupyter-config
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
```

## Collecting output

When we execute code, the kernel broadcasts its output as messages on the IOPub channel. We turn these into `ReplOutput` values:

| message          | kind                 | data                                  |
|------------------|----------------------|---------------------------------------|
| `stream`         | `stdout` or `stderr` | `text/plain`                          |
| `execute_result` | `result`             | MIME bundle                           |
| `display_data`   | `display`            | MIME bundle                           |
| `error`          | `error`              | traceback as `text/plain`, ANSI stripped |

Streamed text arrives in chunks, so consecutive chunks on the same stream are merged. A `clear_output` message drops what we have so far. With `wait: true` it drops it only when the next output arrives (used for animations and progress bars).

Jupyter sends JSON MIME types (like `application/json`) as objects rather than strings. We serialize them so a MIME bundle is always a `dict[str, str]`.

```python
#| id: jupyter-collect
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
```

## Running the kernel

`jupyter_client` does the heavy lifting. `start_new_kernel` starts the kernel and waits until it's ready. `execute_interactive` runs one command, passes each IOPub message to our collector, and returns when the kernel replies. The context manager has the same signature as `repl`: it yields a function that evaluates a `ReplCommand`.

```python
#| id: jupyter-kernel
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
```

## Synthesis

The `jupyter_client` import is the only thing that needs the optional dependency, and this module is only imported when a session asks for the Jupyter backend.

```python
#| file: src/repl_session/jupyter.py
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

<<jupyter-collect>>
<<jupyter-kernel>>
```
