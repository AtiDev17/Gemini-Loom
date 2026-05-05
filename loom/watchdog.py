"""Watchdog that monitors Gemini CLI's stream-json output and stderr."""

import asyncio
import platform
import signal
import json
import time
from pathlib import Path

_GEMINI_PS1_PATH = Path.home() / "AppData" / "Roaming" / "npm" / "gemini.ps1"


class GeminiRunner:
    def __init__(self, prompt: str, timeout_seconds=120):
        self.prompt = prompt
        self.timeout = timeout_seconds
        self.last_event_time = time.time()
        self.process = None
        self.hang_detected = False
        self.rate_limited = False
        self._stderr_lines = []
        self._received_result = False
        self._killed_by_watchdog = False

    async def _read_stdout(self, stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            line = line.decode("utf-8").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.last_event_time = time.time()
            event_type = event.get("type", "?")
            if event_type == "message" and event.get("delta"):
                print(event["content"], end="", flush=True)
            elif event_type == "result":
                if event.get("status") == "success":
                    self._received_result = True
                print(f"\n✅ {event.get('status', 'done')} - {event.get('stats', {})}")
        return

    async def _read_stderr(self, stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            line = line.decode("utf-8").strip()
            if not line:
                continue
            self._stderr_lines.append(line)
            if "status 429" in line or "RESOURCE_EXHAUSTED" in line:
                self.rate_limited = True

    async def _watchdog_loop(self):
        while True:
            await asyncio.sleep(1)
            if time.time() - self.last_event_time > self.timeout:
                # Only kill if still running and no result seen
                if self.process is None or self.process.returncode is not None:
                    return
                if self._received_result:
                    return
                self._killed_by_watchdog = True
                self.process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.process.kill()
                break

    async def run(self):
        if platform.system() == "Windows" and _GEMINI_PS1_PATH.exists():
            gemini_path = str(_GEMINI_PS1_PATH)
        else:
            import shutil
            gemini_path = shutil.which("gemini")
            if gemini_path is None:
                raise FileNotFoundError("gemini CLI not found")

        if gemini_path.endswith(".ps1"):
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", gemini_path,
                "-p", self.prompt,
                "-o", "stream-json",
            ]
        else:
            cmd = ["gemini", "-p", self.prompt, "-o", "stream-json"]

        self.process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        assert self.process.stdout is not None
        assert self.process.stderr is not None

        stdout_task = asyncio.create_task(self._read_stdout(self.process.stdout))
        stderr_task = asyncio.create_task(self._read_stderr(self.process.stderr))
        watchdog_task = asyncio.create_task(self._watchdog_loop())
        process_wait = asyncio.create_task(self.process.wait())

        done, pending = await asyncio.wait(
            [process_wait, watchdog_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        # Determine true hang status
        self.hang_detected = self._killed_by_watchdog and not self._received_result
        if self.hang_detected:
            print("\n💢 Hang detected. Terminating...")   # print only on real hang

        exit_code = self.process.returncode if self.process.returncode is not None else -1
        if self.hang_detected:
            exit_code = -1
        return exit_code, self.hang_detected, self.rate_limited