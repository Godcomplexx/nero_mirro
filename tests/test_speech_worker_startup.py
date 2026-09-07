from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SpeechWorkerStartupTest(unittest.TestCase):
    def test_direct_launch_answers_health_without_project_pythonpath(self) -> None:
        worker = Path(__file__).resolve().parents[1] / "runtime/speech_worker/worker.py"
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        request = {"id": "startup-check", "action": "health", "payload": {}}

        with tempfile.TemporaryDirectory() as working_directory:
            process = subprocess.run(
                [sys.executable, str(worker)],
                input=json.dumps(request) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=working_directory,
                env=environment,
                timeout=60,
            )

        self.assertEqual(process.returncode, 0, process.stderr)
        response = json.loads(process.stdout)
        self.assertEqual(response["id"], request["id"])
        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["worker_available"])
        self.assertEqual(response["result"]["default_model"], "v3_rnnt")


if __name__ == "__main__":
    unittest.main()
