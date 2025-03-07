# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: E501
# pylint: disable=redefined-outer-name,broad-exception-caught

# Standard
import json

# Third Party
import pytest
import transformers

# Local
from granite_io import make_io_processor
from granite_io.backend import Backend
from granite_io.io.granite_3_2 import (
    _COT_END,
    _COT_END_ALTERNATIVES,
    _COT_START,
    _COT_START_ALTERNATIVES,
    _MODEL_NAME,
    GRANITE_3_2_2B_HF,
    Granite3Point2InputOutputProcessor,
    _Granite3Point2Inputs,
)
from granite_io.io.granite_output_parser import (
    _CITATION_START,
    _HALLUCINATION_START,
)
from granite_io.types import (
    AssistantMessage,
    ChatCompletionInputs,
    ChatCompletionResults,
    Citation,
    Document,
    GenerateResult,
    GenerateResults,
    Hallucination,
    UserMessage,
)

## Helpers #####################################################################

# All the different chat completion requests that are tested in this file, serialized as
# JSON strings. Represented as a dictionary instead of a list so that pytest output will
# show the short key instead of the long value when referencing a single run of a test
INPUT_JSON_STRS = {
    "simple": """
{
    "messages":
    [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing great. How can I help you today?"},
        {"role": "user", "content": "I'd like to show off how chat templating works!"}
    ]
}
""",
    "thinking_tag": """
{
    "messages":
    [
        {"role": "user", "content": "How much wood could a wood chuck chuck?"}
    ],
    "thinking": true
}
""",
}


@pytest.fixture(scope="session", params=INPUT_JSON_STRS)
def input_json_str(request: pytest.FixtureRequest) -> str:
    """Pytest fixture that allows us to run a given test case repeatedly with multiple
    different chat completion requests."""
    return INPUT_JSON_STRS[request.param]


@pytest.fixture(scope="session")
def tokenizer() -> transformers.PreTrainedTokenizerBase:
    model_path = GRANITE_3_2_2B_HF
    try:
        ret = transformers.AutoTokenizer.from_pretrained(
            model_path, local_files_only=False
        )
    except Exception as e:
        pytest.skip(f"No tokenizer for {model_path}: {e}")
    return ret


msg = UserMessage(content="Hello")
no_thinking_input = ChatCompletionInputs(messages=[msg])
thinking_input = ChatCompletionInputs(messages=[msg], thinking=True)

thought = "Think think"
response = "respond respond"
pre_thought = "something before"
no_cot_output = f"{thought} {response}"
no_thinking_output = f"{thought} {_COT_END} {response}"
no_response_output = f"{_COT_START}\n\n{response}"
cot_output = f"{_COT_START}\n\n{thought}\n{_COT_END}\n\n{response}"
cot_alt_output = f"{_COT_START_ALTERNATIVES[-1]}\n\n{thought}\n{_COT_END_ALTERNATIVES[-1]}\n\n{response}"
cot_mixed_output = (
    f"{_COT_START}\n\n{thought}\n{_COT_END_ALTERNATIVES[-1]}\n\n{response}"
)
cot_pre_output = (
    f"{pre_thought} {_COT_START} {thought} {_COT_END_ALTERNATIVES[-1]} {response}"
)

no_constituent_output = "Mad about dog!"
citation_example = '<co>1</co> Document 1: "Dog info"'
citation_output = (
    f"{no_constituent_output}<co>1</co>\n\n{_CITATION_START}\n\n{citation_example}\n\n"
)
hallucination_example = "1. Risk low: Mad about dog"
citation_hallucination_output = (
    f"{citation_output}{_HALLUCINATION_START}\n\n{hallucination_example}\n\n"
)
expected_citation = Citation(
    citation_id="1",
    doc_id="1",
    context_text="Dog info",
    context_begin=0,
    context_end=8,
    response_text="Mad about dog!",
    response_begin=0,
    response_end=14,
)
expected_document = Document(doc_id="1", text="Dog info")
expected_hallucination = Hallucination(
    hallucination_id="1",
    risk="low",
    response_text="Mad about dog",
    response_begin=0,
    response_end=13,
)
## Tests #######################################################################


def test_read_inputs(input_json_str):
    """
    Verify that the dataclasses for the Granite 3.2 I/O processor can parse Granite 3.2 JSON
    """
    print(f"{input_json_str=}")
    input_json = json.loads(input_json_str)
    input_obj = ChatCompletionInputs.model_validate(input_json)
    input_obj_2 = ChatCompletionInputs.model_validate_json(input_json_str)

    assert input_obj == input_obj_2

    # Parse additional Granite-specific fields
    granite_input_obj = _Granite3Point2Inputs.model_validate(input_obj.model_dump())

    # Verify that we can convert back to JSON without crashing
    granite_input_obj.model_dump_json()
    input_obj.model_dump_json()


def test_same_input_string(
    tokenizer: transformers.PreTrainedTokenizerBase, input_json_str: str
):
    """
    Verify that the I/O processor produces the exact same input string as the Jinja
    template that ships with the model.
    """

    # First apply the Jinja template
    input_json = json.loads(input_json_str)
    input_kwargs = input_json.copy()
    del input_kwargs["messages"]
    transformers_str = tokenizer.apply_chat_template(
        input_json["messages"],
        **input_kwargs,
        tokenize=False,
        add_generation_prompt=True,
    )

    # Then compare against the input processor
    inputs = ChatCompletionInputs.model_validate_json(input_json_str)
    io_proc_str = Granite3Point2InputOutputProcessor().inputs_to_string(inputs)

    assert io_proc_str == transformers_str


def test_basic_inputs_to_string():
    """
    Basic test against canned output in case the developer doesn't have a way to load
    an actual Granite 3.2 tokenizer for output comparisons.

    Chat input:

    chat = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing great. How can I help you today?"},
        {"role": "user", "content": "I'd like to show off how chat templating works!"},
    ]

    Expected similar (dates will vary) chat template request generated:

    <|start_of_role|>system<|end_of_role|>Knowledge Cutoff Date: April 2024.
    Today's Date: February 17, 2025.
    You are Granite, developed by IBM. You are a helpful AI assistant.<|end_of_text|>
    <|start_of_role|>user<|end_of_role|>Hello, how are you?<|end_of_text|>
    <|start_of_role|>assistant<|end_of_role|>I'm doing great. How can I help you today?<|end_of_text|>
    <|start_of_role|>user<|end_of_role|>I'd like to show off how chat templating works!<|end_of_text|>
    """
    chatRequest = Granite3Point2InputOutputProcessor().inputs_to_string(
        inputs=ChatCompletionInputs(
            messages=[
                UserMessage(content="Hello, how are you?"),
                AssistantMessage(content="I'm doing great. How can I help you today?"),
                UserMessage(content="I'd like to show off how chat templating works!"),
            ]
        ),
        add_generation_prompt=False,
    )
    print(f"Chat request: {chatRequest}")

    chatReqStart = "<|start_of_role|>system<|end_of_role|>Knowledge Cutoff Date:"
    assert chatRequest.startswith(chatReqStart)

    chatReqModelMsg = "You are Granite, developed by IBM. You are a helpful AI assistant.<|end_of_text|>"
    assert chatReqModelMsg in chatRequest

    chatReqBody = """\
<|start_of_role|>user<|end_of_role|>Hello, how are you?<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>I'm doing great. How can I help you today?<|end_of_text|>
<|start_of_role|>user<|end_of_role|>I'd like to show off how chat templating works!<|end_of_text|>"""
    assert chatReqBody in chatRequest

    assert chatRequest.endswith("")


# Session scope for asyncio because the tests in this class all share the same vLLM
# backend
@pytest.mark.asyncio(loop_scope="session")
async def test_run_transformers(
    io_processor_transformers: Granite3Point2InputOutputProcessor, input_json_str: str
):
    inputs = ChatCompletionInputs.model_validate_json(input_json_str)
    io_processor = make_io_processor(_MODEL_NAME, backend=backend_x)
    results: ChatCompletionResults = io_processor.create_chat_completion(inputs)

    assert isinstance(results, ChatCompletionResults)
    assert len(results.results) == 1
    # TODO: Verify outputs in greater detail


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(
    reason="APIConnectionError, but OpenAI tests are optional.",
    raises=APIConnectionError,
)
def test_cot_parsing(inputs, output, exp_thought, exp_resp):
    """Test the parsing logic for CoT reasoning output"""
    proc = Granite3Point2InputOutputProcessor()
    generated = GenerateResults(
        results=[
            GenerateResult(
                completion_string=output, completion_tokens=[], stop_reason="?"
            )
        ]
    )
    result = proc.output_to_result(generated, inputs).results[0].next_message
    assert result.reasoning_content == exp_thought
    assert result.content == exp_resp
    assert result.raw == output


@pytest.mark.parametrize(
    [
        "inputs",
        "output",
        "exp_document",
        "exp_citation",
        "exp_hallucination",
        "exp_resp",
    ],
    [
        # No constituents
        (no_thinking_input, no_constituent_output, [], [], [], no_constituent_output),
        # Citation
        (
            no_thinking_input,
            citation_output,
            [expected_document],
            [expected_citation],
            [],
            no_constituent_output,
        ),
        # Citation and hallucination
        (
            no_thinking_input,
            citation_hallucination_output,
            [expected_document],
            [expected_citation],
            [expected_hallucination],
            no_constituent_output,
        ),
    ],
)
def test_citation_hallucination_parsing(
    inputs, output, exp_document, exp_citation, exp_hallucination, exp_resp
):
    """Test the parsing logic for Rag and hallucinations output"""
    proc = Granite3Point2InputOutputProcessor()
    generated = GenerateResults(
        results=[
            GenerateResult(
                completion_string=output, completion_tokens=[], stop_reason="?"
            )
        ]
    )
    result = proc.output_to_result(generated, inputs).results[0].next_message
    assert result.content == exp_resp
    assert result.citations == exp_citation
    assert result.documents == exp_document
    assert result.hallucinations == exp_hallucination
