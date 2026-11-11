'''Check the student retry example without sending API requests.'''

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google.genai import errors
from pydantic import ValidationError

import retry_example
import test_gemini_syllabus


SUCCESS_JSON = (
	'{"grade_weights": [], "objectives": [], '
	'"assignment_dates": [], "administrative_dates": []}'
)


class FakeModels:
	'''Return queued API outcomes and count requests.'''

	def __init__(self, outcomes: list[object]) -> None:
		'''Store response text and errors in request order.'''

		self.outcomes = outcomes
		self.calls = []
		return None

	def generate_content(self, **kwargs: object) -> SimpleNamespace:
		'''Return the next response or raise the next error.'''

		self.calls.append(kwargs)
		outcome = self.outcomes.pop(0)
		if isinstance(outcome, Exception):
			raise outcome
		return SimpleNamespace(text=outcome)


class FakeClient:
	'''Provide the small client interface used by the example.'''

	def __init__(self, outcomes: list[object]) -> None:
		'''Create a fake model endpoint and track closing.'''

		self.models = FakeModels(outcomes)
		self.closed = False
		return None

	def close(self) -> None:
		'''Record that the example closed its client.'''

		self.closed = True
		return None


def api_error(code: int) -> errors.APIError:
	'''Create a Gemini HTTP error with the given status code.'''

	return errors.APIError(code, {'error': {'message': 'temporary'}})


class RetryExampleTests(unittest.TestCase):
	'''Check the bounded retry policy and copied request contract.'''

	def setUp(self) -> None:
		'''Create one disposable PDF for each test.'''

		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		self.pdf_path = Path(directory.name) / 'example.pdf'
		self.pdf_path.write_bytes(b'%PDF-1.4')
		return None

	def test_retry_then_success(self) -> None:
		'''Retry one 503 and disable hidden SDK retries.'''

		fake = FakeClient([api_error(503), SUCCESS_JSON])
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake)
				as client_constructor,
			patch.object(retry_example.time, 'sleep') as sleep,
		):
			result = retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(result.grade_weights, [])
		self.assertEqual(len(fake.models.calls), 2)
		sleep.assert_called_once_with(4)
		options = client_constructor.call_args.kwargs['http_options']
		self.assertEqual(options.retry_options.attempts, 1)
		self.assertTrue(fake.closed)
		return None

	def test_exhausted_retries(self) -> None:
		'''Stop after three temporary HTTP failures.'''

		fake = FakeClient([api_error(503) for _ in range(3)])
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake),
			patch.object(retry_example.time, 'sleep') as sleep,
			contextlib.redirect_stdout(io.StringIO()),
			self.assertRaises(errors.APIError),
		):
			retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(len(fake.models.calls), 3)
		self.assertEqual(
			[call.args[0] for call in sleep.call_args_list], [4, 8]
		)
		self.assertTrue(fake.closed)
		return None

	def test_rate_limit_error_retries(self) -> None:
		'''Treat HTTP 429 as a temporary failure with a bounded retry.'''

		fake = FakeClient([api_error(429), SUCCESS_JSON])
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake),
			patch.object(retry_example.time, 'sleep') as sleep,
			contextlib.redirect_stdout(io.StringIO()),
		):
			retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(len(fake.models.calls), 2)
		sleep.assert_called_once_with(4)
		return None

	def test_non_retryable_error(self) -> None:
		'''Stop immediately on HTTP 400.'''

		fake = FakeClient([api_error(400)])
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake),
			patch.object(retry_example.time, 'sleep') as sleep,
			contextlib.redirect_stdout(io.StringIO()),
			self.assertRaises(errors.APIError),
		):
			retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(len(fake.models.calls), 1)
		sleep.assert_not_called()
		return None

	def test_invalid_output(self) -> None:
		'''Do not retry a response that fails schema validation.'''

		fake = FakeClient(['{}'])
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake),
			patch.object(retry_example.time, 'sleep') as sleep,
			contextlib.redirect_stdout(io.StringIO()),
			self.assertRaises(ValidationError),
		):
			retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(len(fake.models.calls), 1)
		sleep.assert_not_called()
		return None

	def test_unexpected_request_error(self) -> None:
		'''Stop on a non-HTTP request exception.'''

		fake = FakeClient([RuntimeError('connection failed')])
		output = io.StringIO()
		with (
			patch.object(retry_example.genai, 'Client', return_value=fake),
			patch.object(retry_example.time, 'sleep') as sleep,
			contextlib.redirect_stdout(output),
			self.assertRaises(RuntimeError),
		):
			retry_example.extract_with_retries(
				self.pdf_path, retry_example.DEFAULT_MODEL, 'fake-key'
			)

		self.assertEqual(len(fake.models.calls), 1)
		self.assertIn('Attempt 1/3', output.getvalue())
		sleep.assert_not_called()
		return None

	def test_prompt_and_schema_match_feasibility_test(self) -> None:
		'''Start with the same extraction contract in both examples.'''

		self.assertEqual(
			retry_example.PROMPT, test_gemini_syllabus.PROMPT
		)
		self.assertEqual(
			retry_example.SyllabusExtraction.model_json_schema(),
			test_gemini_syllabus.SyllabusExtraction.model_json_schema(),
		)
		return None

	def test_missing_key_stops_before_client_creation(self) -> None:
		'''Reject missing configuration without attempting a request.'''

		args = SimpleNamespace(
			pdf=self.pdf_path, model=retry_example.DEFAULT_MODEL
		)
		with (
			patch.object(retry_example, 'parse_args', return_value=args),
			patch.object(retry_example, 'load_dotenv'),
			patch.object(retry_example.os, 'getenv', return_value=None),
			patch.object(retry_example.genai, 'Client') as client_constructor,
			contextlib.redirect_stdout(io.StringIO()),
		):
			status = retry_example.main()

		self.assertEqual(status, 2)
		client_constructor.assert_not_called()
		return None


if __name__ == '__main__':
	unittest.main()
