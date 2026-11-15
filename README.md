# REPL Session

[![docs](https://github.com/entangled/repl-session/actions/workflows/pages.yml/badge.svg)](https://github.com/entangled/repl-session/actions/workflows/pages.yml)
[![Static Badge](https://img.shields.io/badge/docs-latest-blue)](https://entangled.github.io/repl-session)

This is script that runs a session on any REPL following a description  in a JSON file. The output contains the commands entered and the results given. This can be useful to drive documentation tests or literate programming tasks. This way we decouple running the commands from rendering or presenting the corresponding results, leading  to better reproducibility, caching output and modularity w.r.t. any other tools that you may use.

This is very similar to running a Jupyter notebook from the console, with the benefit that you don't need a Jupyter kernel available for the language you're using. The downside is that REPLs can be messy to interact with.

## Is this for you?

This is only really useful if you're hacking together a literate programming environment similar to [Entangled](https://entangled.github.io). Suppose you have your documentation written in Markdown, ready for rendering with MkDocs or Pandoc. You want to automatically evaluate some expressions in this document as if they're entered in a REPL and process the results for inclusion in the document generator. Here `repl-session` is a nicely confined command-line tool, so its easy to integrate into a build pipeline.

## How does it work?

The REPL of your choice is started and interacted with through the `pexpect` library. All I/O is dealt with through `msgspec`.

The preferred way to solve this is by using `jupyter-client` in combination with an existing Jupyter kernel. However, not all languages have a Jupyter kernel available, and developing one takes a bit more than configuring `pexpect` for an existing REPL. If a kernel is available for your language, you can use it through the optional Jupyter backend: `pip install repl-session[jupyter]`, then see [the Jupyter backend docs](https://entangled.github.io/repl-session/jupyter).

## Install

Install with,

```bash
pip install repl-session
```

Or equivalent Poetry, Astral Uv, Hatch or Conda commands.

## Documentation

The full documentation is available at [entangled.github.io/repl-session](https://entangled.github.io/repl-session).

## Examples

Here are some examples where we could interact with a REPL successfully. In general, the less intricate the REPL the better the results.

### Chez Scheme

I like to work with [Chez Scheme](https://cisco.github.io/ChezScheme/). Suppose I want to document an interactive session. This can be done:

```yaml
#| file: test/scheme.yml
config:
  command: "scheme --eedisable"
  first_prompt: "> "
  change_prompt: '(waiter-prompt-string "{key}>")'
  prompt: "{key}> "
  # continuation_prompt: ""
commands:
  - command: (* 6 7)
  - command: |
      (define (fac n init)
        (if (zero? n)
          init
          (fac (- n 1) (* init n)))))
  - command: (fac 10 1)
```

Passing this to `repl-session`, it will start the Chez Scheme interpreter, waiting for the `>` prompt to appear. It then changes the prompt to a generated `uuid4` code, for instance `27e87a8a-742c-4501-b05d-b05814f5a010> `. This will make sure that we can't accidentally match something else for an interactive prompt (imagine we're generating some XML!). Running this should give:

```bash
repl-session < test/scheme.yml | jq '.commands.[].output'
```

```
"42"
null
"3628800"
```

### Lua

This looks very similar to the previous example:

```yaml
#| file: test/lua.yml
config:
  command: "lua"
  first_prompt: "> "
  change_prompt: '_PROMPT = "{key}> "; _PROMPT2 = "{key}+ "'
  prompt: "{key}> "
  continuation_prompt: "{key}\\+ "
  strip_ansi: true
commands:
  - command: 6 * 7
  - command: '"Hello" .. ", " .. "World!"'
  - command: |
      function fac(n, m)
          if m == nil then
              return fac(n, 1)
          end
          if n == 0 then
              return m
          else
              return fac(n-1, m*n)
          end
      end
  - command: fac(10)
```

The Lua REPL is not so nice. It sends ANSI escape codes and those need to be filtered out.

```bash
repl-session < test/lua.yml | jq '.commands.[].output'
```

```
"42"
"Hello, World!"
null
"3628800"
```

### Python

The Python REPL got a revision in version 3.13, with lots of colour and ANSI codes.

```yaml
#| file: test/python.yml
config:
  command: python -q
  first_prompt: ">>>"
  change_prompt: 'import sys; sys.ps1 = "{key}>>> "; sys.ps2 = "{key}+++ "'
  prompt: "{key}>>> "
  continuation_prompt: "{key}\\+\\+\\+ "
  environment:
    NO_COLOR: "1"
    PYTHON_BASIC_REPL: "1"
commands:
  - command: print("Hello, World!")
  - command: 6 * 7
  - command: |
      def fac(n):
          for i in range(1, n):
              n *= i
          return n
  - command: fac(10)
```

```bash
repl-session < test/python.yml | jq '.commands.[].output'
```

```
"Hello, World!"
"42"
null
"3628800"
```

## Input/Output structure

The user can configure how the REPL is called and interpreted. The `backend` field picks between this `pexpect` based REPL backend (`backend: repl`, the default) and the Jupyter backend (`backend: jupyter`).

```python
#| id: input-data
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
```

Then, a session is a list of commands. Each command should be a UTF-8 string, and we allow to attach some meta-data like expected MIME type for the output. We can also pass an expected output in the case of a documentation test. If `output` was already given on the input, it is  moved to `expected`. This way it becomes really easy to setup regression tests on your documentation. Just rerun on the generated output file.

The `output` field only holds the representation matching `output_type`. The `outputs` field records everything a command produced, in order. Each item has a `kind` (`result`, `display`, `stdout`, `stderr` or `error`) and a MIME bundle `data` with one or more representations of the same output. A Jupyter kernel may return `text/plain`, `text/html` and `image/png` together, for example. The REPL backend only sees terminal text, so it always gives a single `result`.

```python
#| id: input-data
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
```

## License and contribution

Licensed under the Apache 2.0 license. Contributions are welcome: if you've succesfully applied `repl-session` to a REPL not listed in the documentation, consider contributing your configuration to the documentation. If your contribution fixes a bug, please first file an issue.
