// Define pServer and pDatabase as text parameters in Power BI. No credentials here.
let
    Source = PostgreSQL.Database(pServer, pDatabase, [CreateNavigationProperties = false]),
    Current = Source{[Schema = "public", Item = "vw_customer_intelligence"]}[Data],
    Typed = Table.TransformColumnTypes(Current, {
        {"customer_id", Int64.Type}, {"monthly_revenue", Currency.Type},
        {"nps_score", Int64.Type}, {"support_tickets", Int64.Type},
        {"risk_score", Int64.Type}, {"pending_actions", Int64.Type},
        {"approved_actions", Int64.Type}, {"snapshot_date", type date},
        {"contract_end", type date}, {"last_contact", type date}
    }),
    UTC = Table.TransformColumns(Typed, {
        {"snapshot_timestamp", each DateTimeZone.RemoveZone(DateTimeZone.ToUtc(_)), type datetime}
    })
in
    UTC
