from mcp.server.mcpserver import MCPServer

from src.config import Settings
from src.database import Database
from src.repositories.customers import CustomerRepository


settings = Settings()

database = Database(settings.database_url.get_secret_value())
customers = CustomerRepository(database)

mcp = MCPServer(
    "customer-intelligence",
    version="0.1.0",
)


@mcp.tool()
def get_customer_by_id(customer_id: int) -> dict:
    """Return the authoritative CRM record for one customer."""
    customer = customers.get_customer_by_id(customer_id)
    return customer.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run(transport="stdio")

