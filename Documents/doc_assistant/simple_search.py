import re

def clean_text(text: str) -> str:
    # Remove Hindi / non-ASCII
    text = re.sub(r"[^\x00-\x7F]+", " ", text)

    # Remove Hindi section labels
    text = re.sub(r"\bHindi\s*:\s*.*", "", text, flags=re.IGNORECASE)

    # Remove extra spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_qa_blocks(text: str):
    """
    Returns list of (question, answer) pairs from exam-style PDFs
    """
    pattern = re.compile(r"Q\d+\.\s*", re.IGNORECASE)
    parts = pattern.split(text)

    blocks = []
    for part in parts:
        if "?" in part:
            q, rest = part.split("?", 1)
            blocks.append((q.strip(), rest.strip()))

    return blocks


def search_answer(text: str, question: str, mode="quick", bullets="no"):
    text = re.sub(r"\s+", " ", text)

    qa_blocks = extract_qa_blocks(text)

    q_words = set(
        w.lower() for w in re.findall(r"\w+", question)
        if len(w) > 3
    )

    best_answer = ""
    best_score = 0

    for q_text, a_text in qa_blocks:
        score = sum(1 for w in q_words if w in q_text.lower())
        if score > best_score:
            best_score = score
            best_answer = a_text

    if not best_answer:
        return "Answer not found in document."

    # Stop at next question if leaked
    best_answer = re.split(r"\bQ\d+\.", best_answer)[0]

    best_answer = clean_text(best_answer)

    # Sentence control
    sentences = re.split(r"(?<=[.!?])\s+", best_answer)

    if mode == "quick":
        sentences = sentences[:2]

    if bullets == "yes":
        return "<br>".join(f"• {s}" for s in sentences if s.strip())

    return " ".join(sentences)
