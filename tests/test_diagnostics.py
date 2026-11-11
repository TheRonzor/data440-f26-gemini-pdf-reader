'''Check selection and display of JSONL run records.'''

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diagnostics


class DiagnosticsTests(unittest.TestCase):
	'''Check log discovery without using the project's real logs.'''

	def test_discovery_order_and_selection(self) -> None:
		'''Include all records in file order and select the third.'''

		with tempfile.TemporaryDirectory() as directory:
			log_dir = Path(directory)
			(log_dir / 'b.jsonl').write_text(
				'{"pdf":"second.pdf","status":"api_error"}\n',
				encoding='utf-8',
			)
			(log_dir / 'a.jsonl').write_text(
				'{"pdf":"first.pdf","status":"success"}\n'
				'\n'
				'{"pdf":"third.pdf","status":"success"}\n',
				encoding='utf-8',
			)
			with patch.object(diagnostics, 'LOG_DIR', log_dir):
				logs = diagnostics.load_logs()

		self.assertEqual(len(logs), 3)
		self.assertEqual([entry.line_number for entry in logs], [1, 3, 1])
		self.assertIn('third.pdf', logs[1].label)
		self.assertIn('second.pdf', logs[2].label)
		output = io.StringIO()
		with contextlib.redirect_stdout(output):
			diagnostics.print_log(logs[2])
		printed_record = json.loads(output.getvalue().split('\n', 1)[1])
		self.assertEqual(printed_record['pdf'], 'second.pdf')
		return None

	def test_empty_and_malformed_logs(self) -> None:
		'''Return no entries when empty and locate invalid JSON.'''

		with tempfile.TemporaryDirectory() as directory:
			log_dir = Path(directory)
			with patch.object(diagnostics, 'LOG_DIR', log_dir):
				self.assertEqual(diagnostics.load_logs(), [])
				(log_dir / 'runs.jsonl').write_text(
					'{invalid json}\n', encoding='utf-8'
				)
				logs = diagnostics.load_logs()

		self.assertEqual(len(logs), 1)
		self.assertIn('invalid JSON', logs[0].label)
		output = io.StringIO()
		with contextlib.redirect_stdout(output):
			diagnostics.print_log(logs[0])
		self.assertIn('runs.jsonl:1', output.getvalue())
		self.assertIn('Invalid JSON', output.getvalue())
		return None


if __name__ == '__main__':
	unittest.main()
