from hypothesis import given ,settings,strategies as st
from app.utils.chunker import chunk_text

# chunk_size=0 or negative causes unbounded recursion in _split() (a chunk
# that's still "too big" after splitting recurses into itself forever) -
# that's a real latent bug too, but settings.CHUNK_SIZE is a fixed positive
# config value in practice, so it's out of scope here rather than silently
# asserted away. Restricting the strategy to >=1 keeps this suite from
# hanging on that unrelated issue.
chunk_sizes = st.integers(min_value=1,max_value=200)
overlaps = st.integers(min_value=0,max_value=50)

@given(text=st.text(min_size=0,max_size=500),chunk_size=chunk_sizes)
@settings(max_examples=300)
def test_chunking_with_no_overlap_never_loses_or_corrupts_content(text,chunk_size):
    chunks = chunk_text(text,chunk_size=chunk_size,chunk_overlap=0)

    # With zero overlap, every chunk is a disjoint slice of the (stripped)
    # input - concatenating them back must reproduce it exactly. This is
    # the property that catches silent corruption like the space-injection
    # bug: any extra/missing/substituted character breaks this equality.
    assert "".join(chunks) == text.strip()

@given(text=st.text(min_size=1,max_size=500),chunk_size=chunk_sizes)
@settings(max_examples=300)
def test_no_chunk_ever_exceeds_chunk_size_with_no_overlap(text,chunk_size):
    chunks=chunk_text(text,chunk_size=chunk_size,chunk_overlap=0)
    assert all(len(c) <= chunk_size for c in chunks)

@given(text=st.text(alphabet=st.just(" "),min_size=0,max_size=20))
def test_whitespace_only_input_return_no_chunks(text):
    assert chunk_text(text,chunk_size=50,chunk_overlap=0) ==[]

@given(text=st.text(min_size=0,max_size=500),chunk_size=chunk_sizes,chunk_overlap=overlaps)
@settings(max_examples=200)
def test_chunking_with_overlap_never_raises_and_never_exceeds_size_plus_overlap(text,chunk_size,chunk_overlap):
    chunks = chunk_text(text,chunk_size=chunk_size,chunk_overlap=chunk_overlap)

    assert all(len(c) <= chunk_size + chunk_overlap for c in chunks)

def test_regression_long_unbroken_run_of_text_is_not_corrupted_with_spaces():
    """
    The exact failure mode found by the property test above, pinned down
    as a concrete example so it can never silently regress: a single long
    token with no spaces, newlines, or ".' anywhere (e.g. a hsah/URL).
    """
    long_token= "a1b2c3d4e5f6" * 5

    chunks = chunk_text(long_token,chunk_size=10,chunk_overlap=0)

    assert "".join(chunks) == long_token
    assert " " not in "".join(chunks)

def test_regression_separator_between_chunks_is_not_silently_dropped():
    """
    The exact failure mode hypothesis found: a chunk boundary that falls
    exactly between two words was dropping the space (or newline, or
    '. ') between them, gluing unrelated words together in the chunked
    text that gets embedded and searched.
    """
    chunks= chunk_text("0 0",chunk_size=1,chunk_overlap=0)

    assert "".join(chunks) == "0 0"

def test_regression_a_seperator_longer_than_chunk_size_does_not_hang():
    """
    A second failure mode found while fixixng the first one: when the
    seperator itself (e.g. "\\n\\n" , 2 characters) is longer than
    chunk_size, naive re-splitting on that separator regenerates the
    identical string forever. This must terminate (via the hard-slice
    fallback) rather than hang or blow the recursion limit.
    
    Padded with real content on both ends so chunk_text()'s leading
    .strip() (a separate, correct behaviour - see
    test_whitespace_only_input_returns_no_chunks above) doesn't remove
    the newline run before it ever reaches this code path.
    """
    text="a" + "\n\n" * 3 + "b"

    chunks = chunk_text(text,chunk_size=1,chunk_overlap=0)

    assert "".join(chunks) == text
    assert all(len(c) <= 1 for c in chunks)

def test_chunk_overlap_actually_repeats_the_tail_of_the_previous_chunk():
    text = "a" * 30
    chunks= chunk_text(text,chunk_size=10,chunk_overlap=3)

    assert len(chunks) > 1
    for prev,curr in zip(chunks,chunks[1:]):
        assert curr.startswith(prev[-3:])
        