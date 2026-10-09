# SPDX-License-Identifier: GPL-3.0-or-later
"""Local-only ssh/scp stand-ins for remote-mode tests; never invoke a shell or network.

The synthetic host maps directly to absolute paths inside remote_dir. Keeping the
same path on both sides lets mock_ue_receiver validate the delivered GLBs normally.
Only the commands used by Batch are accepted; all other hosts/paths/commands fail.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from tempfile import TemporaryDirectory


class FakeSSH:
    host = "blsync-test"

    def __init__(self, parent):
        self.parent = Path(parent)

    def __enter__(self):
        self.tmp = TemporaryDirectory(prefix="fake ssh ", dir=self.parent)
        self.root = Path(self.tmp.name)
        self.bin_dir = self.root / "bin"
        self.remote_dir = self.root / "remote host" / "live batch"
        self.log = self.root / "commands.jsonl"
        self.bin_dir.mkdir()
        self.remote_dir.mkdir(parents=True)
        source = "#!" + sys.executable + "\n" + Path(__file__).read_text(encoding="utf-8")
        for name in ("ssh", "scp"):
            wrapper = self.bin_dir / name
            wrapper.write_text(source, encoding="utf-8")
            wrapper.chmod(0o700)
        values = {
            "PATH": str(self.bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            "BLSYNC_FAKE_ROOT": str(self.remote_dir),
            "BLSYNC_FAKE_LOG": str(self.log),
        }
        self.previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        return self

    def __exit__(self, *exc):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def commands(self, operation):
        if not self.log.exists():
            return []
        return [row for line in self.log.read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))["operation"] == operation]


def remote_path(value):
    path = Path(value)
    root = Path(os.environ["BLSYNC_FAKE_ROOT"]).resolve()
    if not path.is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError("path is outside the fake remote directory")
    return path.resolve()


def run(tool, args):
    if tool == "scp":
        if len(args) != 3 or args[0] != "-q":
            raise ValueError("unsupported scp arguments")
        host, separator, destination = args[2].partition(":")
        if not separator or host != FakeSSH.host:
            raise ValueError("unknown fake host")
        shutil.copyfile(args[1], remote_path(destination))
        operation = "copy"
    elif tool == "ssh":
        if len(args) != 2 or args[0] != FakeSSH.host:
            raise ValueError("unknown fake host or ssh arguments")
        command = shlex.split(args[1])
        if len(command) == 3 and command[:2] == ["mkdir", "-p"]:
            remote_path(command[2]).mkdir(parents=True, exist_ok=True)
            operation = "mkdir"
        elif len(command) == 2 and command[0] == "cat":
            sys.stdout.buffer.write(remote_path(command[1]).read_bytes())
            operation = "read"
        elif (len(command) == 7 and command[:2] == ["cat", ">"]
              and command[3:5] == ["&&", "mv"] and command[2] == command[5]):
            temporary, destination = remote_path(command[2]), remote_path(command[6])
            temporary.write_bytes(sys.stdin.buffer.read())
            os.replace(temporary, destination)
            operation = "write"
        else:
            raise ValueError("unsupported fake ssh command")
    else:
        raise ValueError("must be invoked as ssh or scp")
    with open(os.environ["BLSYNC_FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"tool": tool, "operation": operation, "args": args}) + "\n")


if __name__ == "__main__":
    try:
        run(Path(sys.argv[0]).name, sys.argv[1:])
    except (OSError, ValueError, KeyError) as error:
        print("fake ssh/scp: " + str(error), file=sys.stderr)
        sys.exit(1)
