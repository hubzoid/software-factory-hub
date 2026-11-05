"""Running the factory's commands locally, without Docker (macOS for now).

When Docker isn't used, the analyst, implementer and reviewer work in a clone
in a work folder on this computer. Every command they run, and the factory's
own Git commands in that clone, run under macOS's built-in sandbox
(``sandbox-exec``, the Seatbelt mechanism Codex and Claude Code also use):

- writes only inside the work folder, which itself can't be moved, removed or
  replaced by a link;
- no reading of /Users (the work folder and toolchain folders on PATH
  excepted), other volumes, or the shared temporary folders;
- no network. The setup command reaches only the package registries of the
  Docker profile (``sandboxes/<profile>.yaml``), through a proxy the factory
  runs for that step alone, so nothing it leaves behind keeps a connection;
- no keychain, no other apps, no other people's terminals, no signals to
  other processes;
- a clean environment: no API keys, tokens or Hubzoid settings.

Docker isolates more: its own file system, CPU and memory limits. On Linux
and Windows, builds need Docker.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
#: Version-manager folders in the home folder that are read whole when a tool
#: on PATH lives there. Any other PATH folder is readable on its own only.
TOOLCHAIN_ROOTS = {".pyenv", ".nvm", ".rbenv", ".asdf", ".rustup", ".volta", ".nodenv", ".goenv", ".jenv",
                   ".sdkman"}
#: Home folders never readable, even when PATH names a folder inside them.
PRIVATE = {".ssh", ".aws", ".azure", ".gnupg", ".config", ".claude", ".codex", ".docker", ".kube", ".netrc",
           ".git-credentials", ".npmrc", ".pypirc", ".hubzoid", ".orbstack", ".fly"}
#: File names never readable anywhere under the home folder, even inside a toolchain folder.
CREDENTIAL_NAMES = (r"(credentials|credentials\.toml|credentials\.json|\.credentials\.json|auth\.json|\.netrc|"
                    r"\.npmrc|\.pypirc|\.git-credentials|hosts\.yml|token|token\.json|config\.yml)")
OUTPUT_LIMIT = 30_000
RAW_LIMIT = 64 * 2**20


def unsupported() -> str | None:
    """Why commands can't run locally, or None when they can."""
    if sys.platform != "darwin":
        return "Builds without Docker run on macOS only for now. On this system, start Docker."
    if not Path(SANDBOX_EXEC).exists():
        return "macOS's sandbox-exec is missing, so commands can't be confined. Start Docker instead."
    if not git_path():
        return "Git is not installed."
    return None


def git_path() -> str | None:
    """Git as the hub finds it, never as a clone's PATH would."""
    return shutil.which("git", path=os.environ.get("PATH") or os.defpath)


def folders(ws: Path) -> dict[str, Path]:
    """The work folder's parts: the clone, the dependencies, a home and a temporary folder."""
    return {"repo": ws / "repo", "env": ws / "env", "home": ws / "home", "tmp": ws / "tmp"}


def _lit(path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _rx(path) -> str:
    """A path as a literal inside a Seatbelt regular expression."""
    return re.sub(r'([\\.^$|?*+()\[\]{}"])', r"\\\1", str(path))


def _host_path() -> list[str]:
    """The hub's PATH, absolute folders only ("." would be the hub's own folder)."""
    return [p for p in (os.environ.get("PATH") or "").split(os.pathsep) if p and os.path.isabs(p)]


def _toolchains() -> list[Path]:
    """Folders under the home folder that hold tools on PATH, readable so those tools keep working."""
    home = Path.home().resolve()
    out: list[Path] = []
    for entry in _host_path():
        try:
            real = Path(entry).resolve()
            rel = real.relative_to(home)
        except (OSError, ValueError):
            continue
        if not rel.parts or rel.parts[0] in PRIVATE:
            continue
        if rel.parts[0] in TOOLCHAIN_ROOTS:
            root = home / rel.parts[0]
        elif rel.parts[:2] == ("Library", "Python"):
            root = home / "Library" / "Python"
        else:
            root = real                     # only the folder on PATH itself
        if root not in out:
            out.append(root)
    return out


def profile(ws: Path, *, proxy_port: int | None = None) -> str:
    """The Seatbelt profile: closed by default, then what builds need."""
    ws = ws.resolve()
    repo = ws / "repo"
    rules = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow signal (target same-sandbox))",
        "(allow process-info* (target same-sandbox))",
        "(allow sysctl-read)",
        "(allow ipc-posix-sem)",
        "(allow ipc-posix-shm)",
        "(allow pseudo-tty)",
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))',
        '(allow mach-lookup (global-name "com.apple.PowerManagement.control"))',
        '(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient"))',
        # Read the system, never people's folders, other volumes or shared temporary folders.
        "(allow file-read*)",
        '(deny file-read* (subpath "/Users"))',
        '(deny file-read* (subpath "/Volumes"))',
        '(deny file-read* (subpath "/private/var/folders"))',
        '(deny file-read* (subpath "/private/tmp"))',
        *[f"(allow file-read* (subpath {_lit(p)}))" for p in _toolchains()],
        f"(deny file-read* (regex #\"^{_rx(Path.home().resolve())}/.*/{CREDENTIAL_NAMES}$\"))",
        "(allow file-read-metadata)",
        # Write only the work folder, which stays where the factory made it: the
        # folder and its clone are never moved, removed or replaced by a link.
        f"(allow file-read* file-write* (subpath {_lit(ws)}))",
        f"(deny file-write-unlink file-write-create (literal {_lit(ws)}) (literal {_lit(repo)}))",
        '(allow file-write-data (literal "/dev/null"))',
        # Terminals this sandbox opened itself, never the person's.
        '(deny file-read* file-write* file-ioctl (regex #"^/dev/tty"))',
        '(allow file-read* file-write* file-ioctl (literal "/dev/ptmx"))',
        '(allow file-read* file-write* file-ioctl (require-all (regex #"^/dev/ttys[0-9]+") '
        '(extension "com.apple.sandbox.pty")))',
    ]
    if proxy_port:
        # The setup step: the registry proxy, and macOS's certificate trust service
        # (pip and Go check HTTPS certificates through it). Never the keychain.
        rules += [f'(allow network-outbound (remote ip "localhost:{int(proxy_port)}"))',
                  '(allow mach-lookup (global-name "com.apple.trustd") (global-name "com.apple.trustd.agent"))']
    return "\n".join(rules)


def environment(ws: Path, *, proxy_port: int | None = None) -> dict[str, str]:
    """A clean environment: the work folder's dependencies first on PATH, the
    work folder as home, and nothing from the hub's own environment but PATH
    and the language. Nothing from the clone itself is ever on PATH."""
    parts = folders(ws)
    path = [str(parts["env"] / "bin"), *_host_path()]
    for fallback in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        if fallback not in path:
            path.append(fallback)
    env = {"PATH": os.pathsep.join(path), "HOME": str(parts["home"]), "TMPDIR": str(parts["tmp"]),
           "LANG": os.environ.get("LANG") or "en_US.UTF-8", "TERM": "dumb", "FACTORY_ENV": str(parts["env"]),
           "PIP_NO_CACHE_DIR": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "NO_COLOR": "1"}
    if (parts["env"] / "bin" / "python").exists():
        env["VIRTUAL_ENV"] = str(parts["env"])
    if proxy_port:
        url = f"http://127.0.0.1:{int(proxy_port)}"
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "npm_config_proxy",
                     "npm_config_https_proxy"):
            env[name] = url
    return env


class _Reader(threading.Thread):
    """Reads a pipe to its end, keeping at most `keep` bytes: all of it when
    `whole`, else the start and the end."""

    def __init__(self, fd: int, keep: int, *, whole: bool):
        super().__init__(daemon=True)
        self.fd, self.keep, self.whole = fd, keep, whole
        self.head, self.tail, self.total = bytearray(), bytearray(), 0

    def run(self) -> None:
        half = self.keep // 2
        while True:
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            self.total += len(chunk)
            if self.whole:
                if len(self.head) < self.keep:
                    self.head += chunk[: self.keep - len(self.head)]
                continue
            room = half - len(self.head)
            if room > 0:
                self.head += chunk[:room]
                chunk = chunk[room:]
            self.tail += chunk
            if len(self.tail) > half:
                del self.tail[: len(self.tail) - half]
        try:
            os.close(self.fd)
        except OSError:
            pass

    def data(self) -> bytes:
        return bytes(self.head) if self.whole else bytes(self.head + self.tail)


def run(ws: Path, argv: list[str] | str, *, proxy_port: int | None = None, timeout: int = 300,
        limit: int = OUTPUT_LIMIT, raw: bool = False) -> dict:
    """Run a command confined to `ws`, in its clone. A string runs in bash.
    Returns exit_code, output (stdout and stderr together, the start and end
    kept within `limit` characters) and timed_out; with `raw`, stdout is
    returned whole as bytes (up to 64 MiB) and stderr apart."""
    reason = unsupported()
    if reason:
        return {"exit_code": 126, "output": reason, "timed_out": False, "stdout": b"", "stderr": reason,
                "overflow": False}
    ws = ws.resolve()
    parts = folders(ws)
    for name in ("home", "tmp"):
        try:
            os.mkdir(parts[name], 0o700)     # never follows a link the agent left there
        except FileExistsError:
            pass
    command = ["/bin/bash", "-c", argv] if isinstance(argv, str) else list(argv)
    out_r, out_w = os.pipe()
    err_r, err_w = os.pipe() if raw else (None, None)
    try:
        proc = subprocess.Popen([SANDBOX_EXEC, "-p", profile(ws, proxy_port=proxy_port), *command],
                                cwd=parts["repo"], env=environment(ws, proxy_port=proxy_port),
                                stdin=subprocess.DEVNULL, stdout=out_w, stderr=err_w if raw else out_w,
                                start_new_session=True)
    finally:
        os.close(out_w)
        if err_w is not None:
            os.close(err_w)
    out = _Reader(out_r, RAW_LIMIT if raw else limit, whole=raw)
    err = _Reader(err_r, 8000, whole=False) if raw else None
    for reader in (out, err):
        if reader:
            reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # Nothing the command started in its own group outlives it.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()
    # A process that left the group may still hold the pipe: the output read so far is the answer.
    for reader in (out, err):
        if reader:
            reader.join(timeout=5)
    if raw:
        data = out.data()
        return {"exit_code": proc.returncode, "stdout": data, "overflow": out.total > len(data),
                "stderr": err.data().decode("utf-8", errors="replace"), "timed_out": timed_out}
    left_out = out.total - len(out.head) - len(out.tail)
    text = (bytes(out.head).decode("utf-8", errors="replace")
            + (f"\n… ({left_out} bytes left out) …\n" if left_out > 0 else "")
            + bytes(out.tail).decode("utf-8", errors="replace"))
    if timed_out:
        text += f"\n(stopped after {timeout} seconds)"
    return {"exit_code": proc.returncode, "output": text, "timed_out": timed_out, "truncated": left_out > 0}


def git(ws: Path, *args: str, timeout: int = 120) -> dict:
    """Git in the clone, confined, by the hub's own Git (never one the clone
    put on PATH), with hooks, fsmonitor and pagers off."""
    return run(ws, [git_path() or "git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                    "-c", "core.pager=cat", "-c", "color.ui=never", *args], timeout=timeout, raw=True)


# -- the setup step's network ---------------------------------------------------------------

def _public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return ip.is_global


class RegistryProxy:
    """An HTTPS proxy on 127.0.0.1 for the setup command alone: it opens
    tunnels to the allowed hosts on port 443 and to public addresses only,
    the same rules as the Docker sandbox's setup proxy. Closing it ends every
    tunnel, so nothing the setup started keeps a connection."""

    def __init__(self, hosts):
        self.hosts = {str(h).lower().rstrip(".") for h in hosts}
        self.port = 0
        self._server: socket.socket | None = None
        self._open: set[socket.socket] = set()
        self._lock = threading.Lock()

    def __enter__(self) -> "RegistryProxy":
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(64)
        self._server, self.port = server, server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self._server is not None:
            self._server.close()
        with self._lock:
            for sock in list(self._open):
                try:
                    sock.close()
                except OSError:
                    pass
            self._open.clear()

    def _track(self, sock: socket.socket) -> socket.socket:
        with self._lock:
            self._open.add(sock)
        return sock

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(self._track(conn),), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        upstream = None
        try:
            conn.settimeout(30)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk or len(head) > 8192:
                    return
                head += chunk
            method, target = (head.split(b"\r\n", 1)[0].decode("latin-1").split(" ") + ["", ""])[:2]
            host, _, port = target.rpartition(":")
            host = host.strip("[]").lower().rstrip(".")
            if method.upper() != "CONNECT" or port != "443" or host not in self.hosts:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            addresses = [a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
            public = [a for a in addresses if _public(a)]
            if not public:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            upstream = self._track(socket.create_connection((public[0], 443), timeout=30))
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            rest = head.split(b"\r\n\r\n", 1)[1]
            if rest:
                upstream.sendall(rest)
            conn.settimeout(300)
            upstream.settimeout(300)
            back = threading.Thread(target=_pump, args=(upstream, conn), daemon=True)
            back.start()
            _pump(conn, upstream)
            back.join(timeout=300)
        except (OSError, ValueError):
            return
        finally:
            for sock in (conn, upstream):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                    with self._lock:
                        self._open.discard(sock)


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass
