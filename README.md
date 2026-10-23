# aws-lambda-uv

An example Python Lambda function that [AWS SAM](https://docs.aws.amazon.com/serverless-application-model/) builds with [uv](https://docs.astral.sh/uv/) instead of pip.

It's a small HTTP API (`POST /greet`) that validates its input with pydantic. pydantic was picked because it has a compiled part (`pydantic-core`), which shows uv fetching the right wheels for Lambda.

## How it works

SAM has a `python-uv` build method. One line in `template.yaml` turns it on:

```yaml
HelloWorldFunction:
  Type: AWS::Serverless::Function
  Metadata:
    BuildMethod: python-uv
  Properties:
    CodeUri: functions/hello_world/
    Handler: app.handler
```

On `sam build`, SAM finds `pyproject.toml` in `CodeUri`, then:

1. exports `uv.lock` to a requirements list, leaving out dependency groups (so `pytest` and `ruff` never reach the zip);
2. runs `uv pip install --target` with `--python-platform` set for the function's architecture and `--python-version` from its runtime;
3. copies the source next to the installed packages.

Because uv picks wheels by platform, an `arm64` function builds on an x86_64 machine (or a Mac) without Docker. Check `.aws-sam/build/HelloWorldFunction/pydantic_core/` after a build: the `.so` is `aarch64-linux-gnu`.

`python-uv` is still a SAM beta feature. `samconfig.toml` sets `beta_features = true` so `sam build` doesn't prompt every time. It needs a recent SAM CLI (this repo pins 1.170.0) and `uv` on your `PATH`.

## Layout

```text
template.yaml                    # SAM template: function, HTTP API, BuildMethod: python-uv
samconfig.toml                   # beta opt-in, build cache, deploy defaults
functions/hello_world/
  pyproject.toml                 # runtime dependencies + a dev group
  uv.lock                        # what SAM installs
  app.py                         # the handler
tests/test_app.py                # unit tests, run against the function's own environment
events/greet.json                # sample API Gateway event for sam local invoke
mise.toml                        # pinned Python, uv and SAM CLI, plus tasks
```

Each function is its own uv project, with its own `pyproject.toml` and `uv.lock`, so each zip only gets that function's dependencies. To add a second function, copy `functions/hello_world`, give it a new name in its `pyproject.toml`, and add a resource with its own `CodeUri`.

## Usage

[mise](https://mise.jdx.dev) installs the pinned tools:

```bash
mise install
mise run install   # uv sync: creates functions/hello_world/.venv with the dev tools
mise run test
mise run lint
mise run build     # sam build
```

Without mise you need Python 3.14, uv and the SAM CLI; the tasks in `mise.toml` show the plain commands.

Add a dependency with uv, then rebuild:

```bash
cd functions/hello_world
uv add httpx           # updates pyproject.toml and uv.lock
uv add --dev moto      # dev only: never deployed
```

### Run it locally

Needs Docker. SAM runs the built zip inside the real Lambda runtime image.

```bash
mise run invoke    # sam local invoke with events/greet.json
mise run api       # sam local start-api, then:
curl -X POST http://127.0.0.1:3000/greet -d '{"name": "Ada", "excited": true}'
```

The function is `arm64`, so on an x86_64 machine Docker needs arm64 emulation (Docker Desktop has it; on Linux, install `qemu-user-static`). On an Apple Silicon Mac it runs natively.

### Deploy

Needs AWS credentials.

```bash
mise run deploy    # sam deploy --guided: asks for the stack name and region the first time
```

The `GreetUrl` output is the endpoint. Remove everything with `mise run delete`.
