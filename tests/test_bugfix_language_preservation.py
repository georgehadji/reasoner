from reasoner.pipeline import ReasonerPipeline


class _MinimalRouter:
    cascading_routing = {}

def test_validate_enhancement_rejects_language_change():
    """
    Ensures that if the LLM attempts to 'helpfully' translate a non-English prompt 
    into English during prompt enhancement, the enhancement is rejected.
    """
    pipeline = ReasonerPipeline(router=_MinimalRouter())

    # Original is in Greek
    original_greek = "Γράψε ένα άρθρο για την ιστορία της Ελλάδας."

    # LLM translates and enhances it into English
    enhanced_english = "Write an article about the history of Greece. It should be detailed, structured, and insightful."

    # Validate should return False because the detected language changes
    is_valid = pipeline._validate_enhancement(original_greek, enhanced_english)
    assert is_valid is False

def test_validate_enhancement_accepts_same_language():
    """
    Ensures that a valid enhancement in the same language is accepted.
    """
    pipeline = ReasonerPipeline(router=_MinimalRouter())

    original_greek = "Γράψε ένα άρθρο για την ιστορία."
    enhanced_greek = "Σε παρακαλώ, γράψε ένα εξαιρετικά αναλυτικό άρθρο για την ιστορία, καλύπτοντας όλες τις πτυχές."

    # Validate should return True (assuming it passes length and fusion guards)
    is_valid = pipeline._validate_enhancement(original_greek, enhanced_greek)
    assert is_valid is True

def test_validate_enhancement_accepts_english_to_english():
    """
    Baseline test: English to English enhancements are accepted.
    """
    pipeline = ReasonerPipeline(router=_MinimalRouter())

    original = "Write an essay about AI."
    # Length is 24. max(100, 24*1.5) = 100.
    enhanced = "Write a detailed essay about the evolution of AI and its future."
    # Length is 64.

    is_valid = pipeline._validate_enhancement(original, enhanced)
    assert is_valid is True
