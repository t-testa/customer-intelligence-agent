import asyncio
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=str(ROOT),
        env={
            "DATABASE_URL": os.environ["DATABASE_URL"],
        },
    )

    print("Starting MCP client...")

    async with Client(server) as client:
        print("MCP connection initialized")
        print("Protocol version:", client.protocol_version)

        listed = await client.list_tools()
        tool_names = [tool.name for tool in listed.tools]

        print("Tools discovered:", tool_names)

        if "get_customer_by_id" not in tool_names:
            raise RuntimeError("Expected MCP tool was not discovered")

        arguments = {"customer_id": 3}

        print("Calling tool: get_customer_by_id")
        print("Input:", arguments)

        result = await client.call_tool(
            "get_customer_by_id",
            arguments,
        )

        print("Tool error:", result.is_error)
        print("Structured result:", result.structured_content)

        if result.is_error:
            raise RuntimeError("MCP tool call returned an error")

        print("MCP TOOL CALL SUCCESS")


if __name__ == "__main__":
    asyncio.run(main())
