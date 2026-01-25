from normativa_processor.chunking.tokenizer_fallback import estimate_tokens_precise


def test_estimate_tokens_precise_counts_words():
    text = "Uno due tre quattro cinque."
    assert estimate_tokens_precise(text) > 0
