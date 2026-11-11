'''Extract one syllabus PDF with a small, visible HTTP retry loop.'''

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 4
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

PROMPT = '''Extract only information supported by this syllabus.
Return the fields required by the response schema.

List each grading category and its percentage of the final grade. Write a
short list of course objectives based on the syllabus, with one objective
per item and no bullet characters in the strings.

Put fixed assignment, exam, and project due dates in assignment_dates.
Put add/drop, withdrawal, holidays, and breaks in administrative_dates.
Keep date_text as written in the syllabus, including any date range.
Do not turn office hours or class meeting times into dates. Do not infer
missing due dates or add an entry for a date that is only "to be announced"
or available from another source. Use an empty list when a category has no
dates. Source pages are numbered starting at 1.'''


class GradeWeight(BaseModel):
	'''Represent one grading category and its weight.'''

	category: str = Field(description='Name of the grading category')
	percentage: float = Field(description='Percent of the final grade')
	source_page: int = Field(description='One-based source PDF page number')


class CourseDate(BaseModel):
	'''Represent one dated syllabus item.'''

	label: str = Field(description='Short name of the dated item')
	date_text: str = Field(description='Date or range as written in the PDF')
	source_page: int = Field(description='One-based source PDF page number')


class SyllabusExtraction(BaseModel):
	'''The fields required for a syllabus extraction.'''

	grade_weights: list[GradeWeight]
	objectives: list[str]
	assignment_dates: list[CourseDate]
	administrative_dates: list[CourseDate]


def parse_args() -> argparse.Namespace:
	'''Read the required PDF path and optional model name.'''

	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('pdf', type=Path)
	parser.add_argument('--model', default=DEFAULT_MODEL)
	return parser.parse_args()


def extract_with_retries(
	pdf_path: Path,
	model: str,
	api_key: str,
) -> SyllabusExtraction:
	'''Retry temporary HTTP errors while extracting one PDF.'''

	# Load the PDF once so every attempt sends the same document.
	pdf_part = types.Part.from_bytes(
		data=pdf_path.read_bytes(),
		mime_type='application/pdf',
	)
	client = genai.Client(
		api_key=api_key,
		# Keep SDK retries off so this loop controls every attempt.
		http_options=types.HttpOptions(
			retry_options=types.HttpRetryOptions(attempts=1),
		),
	)
	try:
		for attempt in range(1, MAX_ATTEMPTS + 1):
			try:
				response = client.models.generate_content(
					model=model,
					contents=[pdf_part, PROMPT],
					config=types.GenerateContentConfig(
						response_mime_type='application/json',
						response_schema=SyllabusExtraction,
					),
				)
			except errors.APIError as error:
				if (
					error.code not in RETRYABLE_HTTP_CODES
					or attempt == MAX_ATTEMPTS
				):
					print(f'Attempt {attempt}/{MAX_ATTEMPTS}: '
						f'HTTP {error.code}; stopping.')
					raise

				delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
				print(f'Attempt {attempt}/{MAX_ATTEMPTS}: '
					f'HTTP {error.code}; retrying in {delay} seconds.')
				time.sleep(delay)
				continue
			except Exception as error:
				print(f'Attempt {attempt}/{MAX_ATTEMPTS}: '
					f'{type(error).__name__}; stopping.')
				raise

			if not response.text:
				print(f'Attempt {attempt}/{MAX_ATTEMPTS}: '
					'invalid response; stopping.')
				raise ValueError('Gemini returned no text.')
			try:
				result = SyllabusExtraction.model_validate_json(response.text)
			except ValidationError:
				print(f'Attempt {attempt}/{MAX_ATTEMPTS}: '
					'invalid response; stopping.')
				raise
			print(f'Attempt {attempt}/{MAX_ATTEMPTS}: success.')
			return result

		# The last failed attempt raises above; this guards that invariant.
		raise RuntimeError('No extraction result after the retry loop.')
	finally:
		client.close()


def main() -> int:
	'''Validate inputs, run the example, and print its result.'''

	args = parse_args()
	pdf_path = args.pdf.resolve()
	if not pdf_path.is_file() or pdf_path.suffix.lower() != '.pdf':
		print(f'PDF file not found: {pdf_path}')
		return 2

	load_dotenv(ROOT / '.env')
	api_key = os.getenv('GEMINI_API_KEY')
	if not api_key:
		print('Set GEMINI_API_KEY in the project .env file first.')
		return 2

	try:
		result = extract_with_retries(pdf_path, args.model, api_key)
	except errors.APIError as error:
		message = str(error.message).replace(api_key, '[REDACTED]')
		print(f'HTTP {error.code}: {message}')
		return 1
	except (ValidationError, ValueError) as error:
		print(f'Invalid response: {error}')
		return 1
	except Exception as error:
		message = str(error).replace(api_key, '[REDACTED]')
		print(f'Request failed: {type(error).__name__}: {message}')
		return 1

	print(result.model_dump_json(indent=2))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
