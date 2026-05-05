import asyncio
import unittest
from unittest.mock import MagicMock, patch
from loom.watchdog import GeminiRunner

class TestGeminiRunner(unittest.IsolatedAsyncioTestCase):
    @patch("asyncio.create_subprocess_exec")
    @patch("shutil.which")
    @patch("platform.system")
    async def test_run_with_model(self, mock_system, mock_which, mock_exec):
        # Setup
        mock_system.return_value = "Linux" # Avoid Windows-specific path logic for simplified test
        mock_which.return_value = "/usr/bin/gemini"
        
        mock_process = MagicMock()
        mock_process.stdout = asyncio.StreamReader()
        mock_process.stderr = asyncio.StreamReader()
        # Feed it some dummy data so it finishes
        mock_process.stdout.feed_data(b'{"type": "result", "status": "success"}\n')
        mock_process.stdout.feed_eof()
        mock_process.stderr.feed_eof()
        
        # Mock wait to return immediately
        async def mock_wait():
            return 0
        mock_process.wait = mock_wait
        mock_process.returncode = 0
        
        mock_exec.return_value = mock_process
        
        # Test
        # This should fail because GeminiRunner.__init__ doesn't accept model yet
        runner = GeminiRunner("test prompt", model="gemini-1.5-pro")
        await runner.run()
        
        # Verify
        args, kwargs = mock_exec.call_args
        self.assertIn("-m", args)
        self.assertIn("gemini-1.5-pro", args)

    @patch("asyncio.create_subprocess_exec")
    @patch("shutil.which")
    @patch("platform.system")
    async def test_run_without_model(self, mock_system, mock_which, mock_exec):
        # Setup
        mock_system.return_value = "Linux"
        mock_which.return_value = "/usr/bin/gemini"
        
        mock_process = MagicMock()
        mock_process.stdout = asyncio.StreamReader()
        mock_process.stderr = asyncio.StreamReader()
        mock_process.stdout.feed_data(b'{"type": "result", "status": "success"}\n')
        mock_process.stdout.feed_eof()
        mock_process.stderr.feed_eof()
        
        async def mock_wait():
            return 0
        mock_process.wait = mock_wait
        mock_process.returncode = 0
        
        mock_exec.return_value = mock_process
        
        # Test
        runner = GeminiRunner("test prompt")
        await runner.run()
        
        # Verify
        args, kwargs = mock_exec.call_args
        self.assertNotIn("-m", args)

if __name__ == "__main__":
    unittest.main()
