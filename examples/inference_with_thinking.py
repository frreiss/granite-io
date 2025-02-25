# SPDX-License-Identifier: Apache-2.0

"""
This example show how to infer or call a model using the framework
and Ollama backend to serve the model.
In this situation the chat request enables thinking mode in the model
to provide better understanding of how the model came to its answer.
"""

# Local
from granite_io import make_backend, make_io_processor
from granite_io.types import ChatCompletionInputs, UserMessage

model_name = "granite3.1"
io_processor = make_io_processor(
    model_name, backend=make_backend("openai", {"model_name": model_name})
)

# With Thinking
inputs = ChatCompletionInputs(
    messages=[
        UserMessage(
            content="What's the fastest way for a seller to visit all the cities in their region?",  # noqa: E501
        )
    ],
    thinking=True,
)
outputs = io_processor.create_chat_completion(inputs)
print(f"ROLE: {outputs.next_message.content}")
print("--------")
print(outputs.next_message.content)
