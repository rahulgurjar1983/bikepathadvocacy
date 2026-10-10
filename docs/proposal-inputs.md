# Public proposal inputs

Use `--proposal-inputs path.json` on `bikeplan run`, `propose` or `report`.
The file may use JSON or YAML. The tool reads it offline. It keeps the
facts and their hash in `frontier.json`, with a delivery record for each
package. Each project sheet shows delivery facts or a reason for an unknown.

The file needs `version: 1` and `public: true`. All extra keys are checked.
Do not put people, home addresses, contact details or private files in it.
Private paths and links to them fail. Owners name public bodies, not people.
Each record needs a stable `id`, a `source` and a `date` in calendar form.
The budget and next decision have a source and date but no ID.

Optional lists are `goals`, `route_options`, `areas`, `stages`, `owners`,
`approvals`, `funding`, `mitigation` and `costs`. A record may refer to
`element_ids` or `project_ids` from the archive. A goal may name
`destination_ids`. A route option may name `goal_ids`. Unknown references
fail. Areas hold a name and an inline Polygon or MultiPolygon in longitude
and latitude. They are inputs for the later area view, not proved impacts.

An owner has an `organization`. An approval has an `authority` and a
`status`: unknown, required, pending, approved or refused. Funding has
`status`: unknown, unfunded, proposed or funded. A mitigation has a
`description`. These facts do not prove consent beyond their stated scope. Scoped owners
and approvals list the works that remain unknown. The public view keeps
approval status beside the authority.

A stage has a `kind`: studies, concept_design, detailed_design or
construction. It has `depends_on`, and may have `owner_id`,
`funding_status`, `funding_source` and `proposed_date`. Cycles and missing
owners fail. A funded stage needs a funding source. All dates stay proposed;
a date alone is never a funded promise. Stage trip outcomes need later checks.

A cost has `element_ids`, `kind`, `low`, `high`, `currency`, `base_year`,
`unit`, `scope` and `exclusions`, plus its source and date. Capital units
are total or per_m; upkeep units are per_year or per_m_year. Rates use
physical work length. The low bound cannot exceed the high bound.
Supported currency codes are AUD, USD, GBP, EUR, CAD and NZD.

Shared works are priced once. Overlapping scopes fail. The tool sums only
one currency, base year and cost kind at a time. A priced scope must be
fully selected. Missing works or mixed bases leave the full range unknown;
known subtotals keep their own scope and exclusions. Even an empty package
has no known cost without a source. Spending, parking loss and weighted
disruption stay distinct. Cost figures have recipes from the archive.

An optional `budget` has currency, base_year and capital_limit. A range
check can say within_range, exceeded or unproved. This check does not prove
funding or that excluded costs fit the bound. It does not change the route
choice. The later option row owns selection under budget limits.

A `next_decision` has kind, ask, required_evidence and
permission_dependencies, and may name owner_id. With no source, the next
ask is a survey or costed concept design. A build request keeps its source
but still needs those checks. See the replay file in
`artifacts/Q2.4/sourced-inputs.json` for public planning context with no
claimed budget, owner or funding. Use this command to check the file and
the fresh real output:

```sh
uv run --frozen python artifacts/Q2.4/collect.py
```
