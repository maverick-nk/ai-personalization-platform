#!/usr/bin/env python3
"""
Export concept quiz results to Anki-compatible tab-separated format.

Usage:
    python scripts/export-anki.py                        # all services
    python scripts/export-anki.py event-ingestion        # one service
    python scripts/export-anki.py --missed-only          # only questions answered incorrectly
    python scripts/export-anki.py --output deck.txt      # custom output path

Output format (Anki tab-separated):
    Question<TAB>Answer<TAB>Tags

Import into Anki:
    File → Import → select the .txt file
    Field separator: Tab
    Fields: Front, Back, Tags
    Allow HTML in fields: yes (for formatting)

Each card:
    Front: question text + answer options A–D
    Back:  correct answer + full explanation + DDIA reference
    Tags:  service::event-ingestion concept::at-least-once-delivery ddia::ch11
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

QUIZ_DIR = Path("docs/sys-design-concepts")
DEFAULT_OUTPUT = Path("docs/sys-design-concepts/anki-export.txt")


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def parse_quiz_file(path: Path) -> list[dict]:
    """Parse a service quiz file into a list of question records."""
    service = path.stem  # e.g. "event-ingestion"
    content = path.read_text()
    cards = []

    # Split into sessions
    sessions = re.split(r"^###\s+\d{4}-\d{2}-\d{2}", content, flags=re.MULTILINE)

    for session_block in sessions:
        # Extract sub-feature label from session header line (first non-empty line)
        subfeature_match = re.search(r"·\s+(.+?)$", session_block, re.MULTILINE)
        subfeature = subfeature_match.group(1).strip() if subfeature_match else "unknown"

        # Find all question blocks within the session
        # Pattern: **Q<N> · [<type>] · <concept>**
        question_blocks = re.split(
            r"\*\*Q\d+\s*·\s*\[([^\]]+)\]\s*·\s*([^\*]+)\*\*",
            session_block
        )

        # re.split with groups gives: [pre, type1, concept1, body1, type2, concept2, body2, ...]
        i = 1
        while i + 2 < len(question_blocks):
            q_type = question_blocks[i].strip()
            concept = question_blocks[i + 1].strip()
            body = question_blocks[i + 2]

            card = parse_question_block(body, service, subfeature, q_type, concept)
            if card:
                cards.append(card)

            i += 3

    return cards


def parse_question_block(body: str, service: str, subfeature: str,
                          q_type: str, concept: str) -> Optional[dict]:
    """Parse a single question block into a card dict."""

    # Extract question text (before the options)
    question_match = re.search(r"^(.+?)(?=\n[-*]\s+[A-D]\))", body, re.DOTALL)
    if not question_match:
        return None
    question_text = question_match.group(1).strip()

    # Extract options A–D
    options = {}
    for opt in re.finditer(r"[-*]\s+([A-D])\)\s+(.+?)(?=\n[-*]\s+[A-D]\)|\n\*\*User answered|$)",
                           body, re.DOTALL):
        options[opt.group(1)] = opt.group(2).strip()

    if len(options) < 4:
        return None

    # Extract user answer and correct answer
    result_match = re.search(
        r"\*\*User answered:\*\*\s*([A-D])\s*·\s*\*\*Correct:\*\*\s*([A-D])\s*·\s*([✓✗])",
        body
    )
    if not result_match:
        return None

    user_answer = result_match.group(1)
    correct_answer = result_match.group(2)
    was_correct = result_match.group(3) == "✓"

    # Extract explanation (blockquote lines starting with >)
    explanation_lines = re.findall(r"^>\s*(.+)$", body, re.MULTILINE)
    explanation = " ".join(explanation_lines).strip()

    # Extract DDIA reference from explanation
    ddia_ref = ""
    ddia_match = re.search(r"DDIA ref:\s*(.+?)(?:\n|$)", body)
    if ddia_match:
        ddia_ref = ddia_match.group(1).strip()
        # Remove from explanation text if present
        explanation = explanation.replace(f"DDIA ref: {ddia_ref}", "").strip()

    # Build tags
    tags = [
        f"service::{slugify(service)}",
        f"concept::{slugify(concept)}",
        f"type::{slugify(q_type)}",
    ]
    if ddia_ref:
        # e.g. "Chapter 11 — Stream Processing" → "ddia::ch11"
        ch_match = re.search(r"Ch(?:apter)?\s*(\d+)", ddia_ref, re.IGNORECASE)
        if ch_match:
            tags.append(f"ddia::ch{ch_match.group(1)}")
    if not was_correct:
        tags.append("missed")

    # Build front (question + options)
    options_text = "\n".join(f"{k}) {v}" for k, v in sorted(options.items()))
    front = f"{question_text}\n\n{options_text}"

    # Build back (correct answer + explanation + reference)
    back_parts = [f"Correct answer: {correct_answer}) {options.get(correct_answer, '')}"]
    if explanation:
        back_parts.append(explanation)
    if ddia_ref:
        back_parts.append(f"DDIA: {ddia_ref}")

    back = "\n\n".join(back_parts)

    return {
        "front": front,
        "back": back,
        "tags": " ".join(tags),
        "service": service,
        "concept": concept,
        "was_correct": was_correct,
    }


def format_for_anki(card: dict) -> str:
    """Format a card as a single tab-separated line for Anki import."""
    # Anki expects newlines as <br> inside fields when using tab-separated import
    front = card["front"].replace("\n", "<br>")
    back = card["back"].replace("\n", "<br>")
    return f"{front}\t{back}\t{card['tags']}"


def main():
    parser = argparse.ArgumentParser(
        description="Export concept quiz results to Anki tab-separated format."
    )
    parser.add_argument(
        "service",
        nargs="?",
        help="Service name to export (e.g. event-ingestion). Omit for all services.",
    )
    parser.add_argument(
        "--missed-only",
        action="store_true",
        help="Only export cards the user answered incorrectly.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if not QUIZ_DIR.exists():
        print(f"Error: {QUIZ_DIR} does not exist. Run /concept-quiz first.", file=sys.stderr)
        sys.exit(1)

    # Collect quiz files
    if args.service:
        target = QUIZ_DIR / f"{args.service}.md"
        if not target.exists():
            print(f"Error: No quiz file found for service '{args.service}'.", file=sys.stderr)
            print(f"Expected: {target}", file=sys.stderr)
            sys.exit(1)
        quiz_files = [target]
    else:
        quiz_files = [
            f for f in QUIZ_DIR.glob("*.md")
            if f.name != "README.md"
        ]
        if not quiz_files:
            print(f"No quiz files found in {QUIZ_DIR}.", file=sys.stderr)
            sys.exit(1)

    # Parse all files
    all_cards = []
    for quiz_file in sorted(quiz_files):
        cards = parse_quiz_file(quiz_file)
        all_cards.extend(cards)
        print(f"  {quiz_file.stem}: {len(cards)} cards parsed")

    # Filter if requested
    if args.missed_only:
        all_cards = [c for c in all_cards if not c["was_correct"]]
        print(f"Filtered to missed-only: {len(all_cards)} cards")

    if not all_cards:
        print("No cards to export.")
        sys.exit(0)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [format_for_anki(card) for card in all_cards]

    with open(args.output, "w", encoding="utf-8") as f:
        # Anki tab-separated header (optional but helpful)
        f.write("#separator:tab\n")
        f.write("#html:true\n")
        f.write("#notetype:Basic\n")
        f.write("#deck:DDIA - Personalization Platform\n")
        f.write("#columns:Front\tBack\tTags\n")
        f.write("\n".join(lines))
        f.write("\n")

    # Summary
    services = sorted({c["service"] for c in all_cards})
    concepts = sorted({c["concept"] for c in all_cards})
    missed = sum(1 for c in all_cards if not c["was_correct"])

    print(f"\nExported {len(all_cards)} cards → {args.output}")
    print(f"  Services:  {', '.join(services)}")
    print(f"  Concepts:  {len(concepts)} unique")
    print(f"  Missed:    {missed} ({100 * missed // len(all_cards)}%)")
    print(f"\nImport into Anki:")
    print(f"  File → Import → {args.output}")
    print(f"  Field separator: Tab")
    print(f"  Fields mapped: Front, Back, Tags")


if __name__ == "__main__":
    main()
