from app.models import Question
from app.services.scoring import calculate_scores, normalize_answer


def question(
    question_id: int,
    number: int,
    section: str,
    correct_answer: str | None,
    *,
    accepted_answers: list[str] | None = None,
) -> Question:
    return Question(
        id=question_id,
        test_id=1,
        number=number,
        section=section,
        question_text="",
        question_type="multiple_choice",
        correct_answer=correct_answer,
        metadata_json={"accepted_answers": accepted_answers or []},
    )


def test_normalize_answer_handles_width_case_and_spacing() -> None:
    assert normalize_answer("  \uff41  ") == "a"
    assert normalize_answer("\u6211   \u662f \u5b66\u751f") == "\u6211 \u662f \u5b66\u751f"
    assert normalize_answer("  ") is None


def test_sections_receive_equal_weight_despite_different_question_counts() -> None:
    questions = [
        question(1, 1, "LISTENING", "A"),
        question(2, 2, "LISTENING", "B"),
        question(3, 3, "LISTENING", "C"),
        question(4, 4, "READING", "A"),
    ]
    result = calculate_scores(
        questions,
        {1: "A", 2: "wrong", 3: "wrong", 4: "A"},
        max_score=200,
    )

    assert result.section_scores["LISTENING"]["score"] == 33.33
    assert result.section_scores["READING"]["score"] == 100.0
    assert result.score == 133.33


def test_ungradable_questions_are_explicit_and_score_zero() -> None:
    expected = "\u6211\u662f\u5b66\u751f"
    questions = [
        question(1, 1, "WRITING", None),
        question(2, 2, "WRITING", None, accepted_answers=[expected]),
    ]
    result = calculate_scores(questions, {1: "anything", 2: f" {expected} "}, 100)

    assert result.score == 50.0
    assert result.section_scores["WRITING"]["gradable"] == 1
    assert result.question_grades[0].is_correct is None
    assert result.question_grades[1].is_correct is True
