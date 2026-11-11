# data440-f26-gemini-pdf-reader

Set up a Gemini API key and store in a `.env` file in the root directory as `GEMINI_API_KEY=`

`test_gemini_syllabi.py`: The test we ran in class. Discovers syallbi in .pdf format in `docs/test_syllabi/`. Each pdf is processed with one call to Gemini.

`retry_example.py`: Includes manual logic for retrying failed attempts.
