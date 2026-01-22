from typing import List, Union
from src.forse_analyze_agent.router.types import ClientMessage
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
import json


def convert_to_openai_messages(
    messages: List[Union[ClientMessage, dict, tuple]],
) -> List[ChatCompletionMessageParam]:
    openai_messages = []

    for message in messages:
        # Handle case where message might be a dict, tuple, or ClientMessage
        if isinstance(message, tuple):
            # Convert tuple to dict if possible (assuming it's (role, content) format)
            if len(message) == 2:
                message = ClientMessage(role=message[0], content=message[1])
            else:
                # Try to convert to dict first
                message = (
                    dict(message)
                    if hasattr(message, "_asdict")
                    else ClientMessage(role="user", content=str(message))
                )
        elif isinstance(message, dict):
            message = ClientMessage(**message)
        elif not isinstance(message, ClientMessage):
            # Try to convert to ClientMessage if it's not already
            if hasattr(message, "__dict__"):
                message = ClientMessage(**message.__dict__)
            elif hasattr(message, "role") and hasattr(message, "content"):
                message = ClientMessage(role=message.role, content=message.content)
            else:
                # Fallback: create a simple user message
                message = ClientMessage(role="user", content=str(message))
        message_parts: List[dict] = []
        tool_calls = []
        tool_result_messages = []

        if message.parts:
            for part in message.parts:
                if part.type == "text":
                    # Ensure empty strings default to ''
                    message_parts.append({"type": "text", "text": part.text or ""})

                elif part.type == "file":
                    if (
                        part.contentType
                        and part.contentType.startswith("image")
                        and part.url
                    ):
                        message_parts.append(
                            {"type": "image_url", "image_url": {"url": part.url}}
                        )
                    elif part.url:
                        # Fall back to including the URL as text if we cannot map the file directly.
                        message_parts.append({"type": "text", "text": part.url})

                elif part.type.startswith("tool-"):
                    tool_call_id = part.toolCallId
                    tool_name = part.toolName or part.type.replace("tool-", "", 1)

                    if tool_call_id and tool_name:
                        should_emit_tool_call = False

                        if part.state and any(
                            keyword in part.state for keyword in ("call", "input")
                        ):
                            should_emit_tool_call = True

                        if part.input is not None or part.args is not None:
                            should_emit_tool_call = True

                        if should_emit_tool_call:
                            arguments = (
                                part.input if part.input is not None else part.args
                            )
                            if isinstance(arguments, str):
                                serialized_arguments = arguments
                            else:
                                serialized_arguments = json.dumps(arguments or {})

                            tool_calls.append(
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": serialized_arguments,
                                    },
                                }
                            )

                        if part.state == "output-available" and part.output is not None:
                            tool_result_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": json.dumps(part.output),
                                }
                            )

        elif message.content is not None:
            message_parts.append({"type": "text", "text": message.content})

        # if not message.parts and message.experimental_attachments:
        #     for attachment in message.experimental_attachments:
        #         if attachment.contentType.startswith('image'):
        #             message_parts.append({
        #                 'type': 'image_url',
        #                 'image_url': {
        #                     'url': attachment.url
        #                 }
        #             })

        #         elif attachment.contentType.startswith('text'):
        #             message_parts.append({
        #                 'type': 'text',
        #                 'text': attachment.url
        #             })

        if message.toolInvocations:
            for toolInvocation in message.toolInvocations:
                tool_calls.append(
                    {
                        "id": toolInvocation.toolCallId,
                        "type": "function",
                        "function": {
                            "name": toolInvocation.toolName,
                            "arguments": json.dumps(toolInvocation.args),
                        },
                    }
                )

        if message_parts:
            if len(message_parts) == 1 and message_parts[0]["type"] == "text":
                content_payload = message_parts[0]["text"]
            else:
                content_payload = message_parts
        else:
            # Ensure that we always provide some content for OpenAI
            content_payload = ""

        openai_message: ChatCompletionMessageParam = {
            "role": message.role,
            "content": content_payload,
        }

        if tool_calls:
            openai_message["tool_calls"] = tool_calls

        openai_messages.append(openai_message)

        if message.toolInvocations:
            for toolInvocation in message.toolInvocations:
                tool_message = {
                    "role": "tool",
                    "tool_call_id": toolInvocation.toolCallId,
                    "content": json.dumps(toolInvocation.result),
                }

                openai_messages.append(tool_message)

        openai_messages.extend(tool_result_messages)

    return openai_messages


def convert_to_langchain_messages(
    messages: List[Union[ClientMessage, dict, tuple]],
) -> List[BaseMessage]:
    """Convert ClientMessage list to LangChain message objects."""
    langchain_messages = []

    # First convert to OpenAI format, then to LangChain
    openai_messages = convert_to_openai_messages(messages)

    for msg in openai_messages:
        role = msg.get("role")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        if role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            if tool_calls:
                # Create AIMessage with tool calls
                langchain_messages.append(
                    AIMessage(
                        content=content or "",
                        tool_calls=[
                            {
                                "name": tc["function"]["name"],
                                "args": json.loads(tc["function"]["arguments"]),
                                "id": tc["id"],
                            }
                            for tc in tool_calls
                        ],
                    )
                )
            else:
                langchain_messages.append(AIMessage(content=content or ""))
        elif role == "system":
            langchain_messages.append(SystemMessage(content=content))
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            langchain_messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                )
            )

    return langchain_messages
