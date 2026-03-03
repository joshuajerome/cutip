# Architecture: Backend Interface

CUTIP's execution layer is abstracted behind `CutipBackend`, an abstract base class in `cutip/backends/base.py`. Podman is the only supported backend. The interface exists to isolate the Podman-specific code and make the execution layer testable independently of the runtime.

---

## The ABC

```python
class CutipBackend(ABC):

    @abstractmethod
    def pull_image(self, card: ImageCard) -> None: ...

    @abstractmethod
    def build_image(
        self,
        card: ImageCard,
        project_root: Path | None = None,
        vars: dict | None = None,
    ) -> None: ...

    @abstractmethod
    def ensure_network(self, card: NetworkCard) -> None: ...

    @abstractmethod
    def create_container(self, card: ContainerCard, image_name: str | None = None) -> str: ...

    @abstractmethod
    def start_container(self, name: str) -> None: ...

    @abstractmethod
    def stop_container(self, name: str) -> None: ...

    @abstractmethod
    def remove_container(self, name: str) -> None: ...

    @abstractmethod
    def container_status(self, name: str) -> str: ...

    @abstractmethod
    def container_logs(self, name: str) -> str: ...
```

---

## Idempotency contract

All `ensure_*` and `create_*` methods must be idempotent — calling them when the resource already exists must be a no-op, not an error. This is how CUTIP achieves safe re-runs:

| Method | Idempotent behaviour |
|---|---|
| `ensure_network` | Return without error if network exists |
| `create_container` | Return without error if container exists |

---

## Implementing a new backend

1. Create `cutip/backends/myruntime.py`
2. Subclass `CutipBackend` and implement all abstract methods
3. Add a `connect()` classmethod that returns a connected instance and raises `CutipError` on failure
4. Wire the new backend into `cutip/cli/commands/run.py` (replace the `PodmanBackend` instantiation with a dispatch on `CUTIP_BACKEND_NAME`)
5. Add the optional dependency to `pyproject.toml` under `[project.optional-dependencies]`

Minimal skeleton:

```python
from cutip.backends.base import CutipBackend
from cutip.utils.exceptions import CutipError

class MyRuntimeBackend(CutipBackend):

    def __init__(self, client) -> None:
        self._client = client

    @classmethod
    def connect(cls) -> "MyRuntimeBackend":
        try:
            import myruntime
            client = myruntime.connect()
        except ImportError as exc:
            raise CutipError("Install cutip[myruntime] to use this backend") from exc
        except Exception as exc:
            raise CutipError(f"Connection failed: {exc}") from exc
        return cls(client=client)

    def pull_image(self, card): ...
    def build_image(self, card, project_root=None, vars=None): ...
    def ensure_network(self, card): ...
    def create_container(self, card, image_name=None): ...
    def start_container(self, name): ...
    def stop_container(self, name): ...
    def remove_container(self, name): ...
    def container_status(self, name) -> str: ...
    def container_logs(self, name) -> str: ...
```

---

## Error handling conventions

- Raise `CutipError` (from `cutip.utils.exceptions`) for all expected failure modes (connection refused, resource not found during removal, build failed)
- Let unexpected exceptions propagate — they will be caught by the CLI and displayed with a traceback
- `stop_container` and `remove_container` should catch and log "not found" errors rather than raising — containers may already be stopped/removed in cleanup paths
