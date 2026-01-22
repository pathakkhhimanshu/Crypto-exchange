import PyPDF2
import re

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_document(path: str) -> str:
    if path.endswith(".txt"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return clean_text(f.read())

    if path.endswith(".pdf"):
        text = ""
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                if page.extract_text():
                    text += page.extract_text() + " "
        return clean_text(text)

    return ""
