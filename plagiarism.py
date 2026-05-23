import fitz  # PyMuPDF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from models.db import get_db
import os


def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text


def calculate_similarity(new_file_path, assignment_id):

    # Extract new submission text
    new_text = extract_text_from_pdf(new_file_path)

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get previous submissions of same assignment
    cursor.execute("""
        SELECT file_name
        FROM submissions
        WHERE assignment_id=%s
    """, (assignment_id,))

    previous_submissions = cursor.fetchall()

    texts = [new_text]

    for sub in previous_submissions:
        old_path = os.path.join("uploads", "submissions", sub["file_name"])
        if os.path.exists(old_path):
            texts.append(extract_text_from_pdf(old_path))

    db.close()

    # If no previous submissions → no similarity
    if len(texts) == 1:
        return 0.0

    vectorizer = TfidfVectorizer().fit_transform(texts)
    vectors = vectorizer.toarray()

    similarity_matrix = cosine_similarity(vectors)

    # Compare new submission (index 0) with others
    similarities = similarity_matrix[0][1:]

    max_similarity = max(similarities) * 100

    return round(max_similarity, 2)